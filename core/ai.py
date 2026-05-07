from __future__ import annotations

import json
import random
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Callable, Literal, Optional

AIProvider = Literal["claude", "openai", "gemini", "deepseek"]

MODELS = {
    "claude": ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-5"],
    "openai": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
    "gemini": ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"],
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat"],
}

ProgressCallback = Optional[Callable[[str], None]]

SYSTEM_PROMPT = """Eres un experto en extracción de datos de laboratorios clínicos de hemodiálisis.
Analiza el PDF completo y devuelve exclusivamente JSON válido, sin markdown.

IMPORTANTE:
- Esta extracción alimentará un Excel SAIRC; no inventes ni completes datos por inferencia.
- Contexto clínico: son pacientes con enfermedad renal crónica en hemodiálisis; muchos valores serán patológicos. Extrae el valor real, no lo corrijas ni lo descartes por estar fuera del rango normal.
- Si un valor no aparece explícitamente o no es legible, usa null.
- No tomes rangos de referencia como resultados.
- Identidad: extrae SOLO el DNI/C.E./documento asociado al paciente. No confundas con CUI, código IPRESS, RUC, número de orden, teléfono, CMP, colegiatura, historia clínica o código de barra.
- Si hay varios números que parecen documentos, llena documentos_detectados y selecciona como documento_identidad el que esté asociado directamente al paciente.
- Conserva los resultados cualitativos como aparecen: NO REACTIVO, NEGATIVO, POSITIVO, REACTIVO, INDETERMINADO.
- En serologías con índice numérico, conserva la interpretación textual si existe; coloca el índice en resultado u observación, pero no reemplaces NO REACTIVO/REACTIVO por el índice cuando la interpretación esté disponible.
- Si una tabla trae columnas PRE DIÁLISIS y POS DIÁLISIS, distingue claramente urea pre y post. No asignes columna post a otros exámenes si no corresponde.
- Si hay valores con asteriscos o marcas de fuera de rango, conserva el número y puedes dejar la marca en observación.
- Lee todas las páginas; un mismo PDF puede tener resultados mensuales, bimestrales o semestrales.

Devuelve este esquema exacto:
{
  "paciente_nombre": string|null,
  "documento_identidad": string|null,
  "documentos_detectados": [string],
  "edad": string|null,
  "sexo": string|null,
  "laboratorio": string|null,
  "fecha_examen": string|null,
  "fecha_toma_muestra": string|null,
  "fecha_emision": string|null,
  "resultados": [
    {
      "analisis": string|null,
      "resultado": string|null,
      "unidades": string|null,
      "rango_referencia": string|null,
      "metodo": string|null,
      "observacion": string|null,
      "confianza": "alta"|"media"|"baja"|null,
      "estado_lectura": "leido"|"dudoso"|"ilegible"|null,
      "observacion_lectura": string|null
    }
  ]
}

Para mejorar auditoría, cuando tengas duda anota en observacion_lectura la página, bloque o texto cercano que sustenta el resultado. Si una fila parece rango de referencia, no la coloques como resultado.

Exámenes prioritarios a extraer cuando existan:
Hemoglobina, Hematocrito, Urea pre, Urea post, Sodio, Potasio, Cloro, Calcio, Fósforo, Albúmina,
TGO/AST, TGP/ALT, Fosfatasa alcalina, Hierro sérico, Ferritina, Transferrina, Saturación de transferrina,
Paratohormona/PTH, HIV, VDRL/RPR/Sífilis, HBsAg, Anti-HBs, Anti-HBc, HCV y HTLV.

Si el documento no tiene resultados confiables, devuelve resultados: [].
"""

USER_PROMPT = "Analiza este informe de laboratorio y extrae los datos en el formato JSON indicado."
INVALID_ANALYSIS_NAMES = {"index", "índice", "indice", "item", "valor", "resultado", "result"}


@dataclass
class AIConfig:
    provider: AIProvider = "gemini"
    model: str = "gemini-2.5-flash"
    api_key: str = ""
    timeout_seconds: int = 120
    max_retries: int = 4
    temperature: float = 0.0
    requests_per_minute: int = 10
    cooldown_on_429_seconds: int = 45
    enable_token_count: bool = False


@dataclass
class TokenUsage:
    provider: str = ""
    model: str = ""
    estimated_input_tokens: int | None = None
    prompt_token_count: int | None = None
    candidates_token_count: int | None = None
    total_token_count: int | None = None
    cached_content_token_count: int | None = None
    cost_estimated_usd: float | None = None
    count_tokens_error: str | None = None
    count_tokens_seconds: float | None = None


@dataclass
class AIResponse:
    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)


MODEL_PRICES_USD_PER_MTOK = {
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-5": {"input": 15.00, "output": 75.00},
    # Referenciales editables. Confirmar precios vigentes del proveedor antes de producción.
    "deepseek-v4-flash": {"input": 0.05, "output": 0.20},
    "deepseek-v4-pro": {"input": 0.14, "output": 0.28},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
}


class AIError(RuntimeError):
    def __init__(self, message: str, *, category: str = "ai_error", status_code: int | None = None, retry_after: int | None = None):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.retry_after = retry_after


class GlobalRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0
        self._last_call_at = 0.0
        self._consecutive_429 = 0

    def wait_for_slot(self, rpm: int, progress: ProgressCallback = None) -> None:
        rpm = max(1, int(rpm))
        min_interval = 60.0 / rpm
        while True:
            with self._lock:
                now = time.time()
                target = max(self._next_allowed_at, self._last_call_at + min_interval)
                wait = target - now
                if wait <= 0:
                    self._last_call_at = now
                    return
            if progress and wait > 1:
                progress(f"Esperando cupo de API ({wait:.1f}s)...")
            time.sleep(min(wait, 1.0))

    def apply_cooldown(self, seconds: int, progress: ProgressCallback = None) -> None:
        seconds = max(1, int(seconds))
        with self._lock:
            self._consecutive_429 += 1
            now = time.time()
            self._next_allowed_at = max(self._next_allowed_at, now + seconds)
            current = self._consecutive_429
        if progress:
            progress(f"Rate limit detectado. Pausa global de {seconds}s (racha 429={current}).")

    def reset_error_streak(self) -> None:
        with self._lock:
            self._consecutive_429 = 0

    def current_streak(self) -> int:
        with self._lock:
            return self._consecutive_429


RATE_LIMITER = GlobalRateLimiter()


def _parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return max(1, int(value))
    try:
        dt = parsedate_to_datetime(value)
        return max(1, int(dt.timestamp() - time.time()))
    except Exception:
        return None


def _post(url: str, headers: dict, payload: dict, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        retry_after = _parse_retry_after(e.headers.get("Retry-After"))
        category = {401: "auth_401", 403: "forbidden_403", 408: "timeout_408", 429: "rate_limit_429"}.get(e.code, f"http_{e.code}")
        raise AIError(f"HTTP {e.code}: {body[:300]}", category=category, status_code=e.code, retry_after=retry_after) from e
    except urllib.error.URLError as e:
        raise AIError(str(e), category="network_error") from e
    except OSError as e:
        raise AIError(str(e), category="network_error") from e


def _extract_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _clean_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = re.sub(r"\s+", " ", value).strip()
        return cleaned or None
    return value


def _normalize_result_item(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    analisis = _clean_value(item.get("analisis"))
    resultado = _clean_value(item.get("resultado"))
    unidades = _clean_value(item.get("unidades"))
    rango = _clean_value(item.get("rango_referencia"))
    if isinstance(analisis, str) and analisis.lower() in INVALID_ANALYSIS_NAMES:
        analisis = None
    if not any([analisis, resultado, unidades, rango]):
        return None
    return {
        "analisis": analisis,
        "resultado": resultado,
        "unidades": unidades,
        "rango_referencia": rango,
        "metodo": _clean_value(item.get("metodo")),
        "observacion": _clean_value(item.get("observacion")),
        "confianza": _clean_value(item.get("confianza")),
        "estado_lectura": _clean_value(item.get("estado_lectura")),
        "observacion_lectura": _clean_value(item.get("observacion_lectura")),
    }


def _quality_meta(data: dict) -> dict:
    resultados = data.get("resultados") or []
    total = len(resultados)
    with_value = sum(1 for r in resultados if r.get("resultado"))
    with_units = sum(1 for r in resultados if r.get("unidades"))
    has_patient = bool(data.get("paciente_nombre"))
    has_date = bool(data.get("fecha_examen") or data.get("fecha_toma_muestra") or data.get("fecha_emision"))
    score = 0
    score += 25 if has_patient else 0
    score += 20 if has_date else 0
    score += 25 if total >= 3 else (10 if total > 0 else 0)
    score += 20 if total and with_value / total >= 0.70 else (10 if with_value else 0)
    score += 10 if total and with_units / total >= 0.50 else 0
    level = "alta" if score >= 75 else ("media" if score >= 50 else "baja")
    return {"quality_score": score, "quality_level": level, "has_patient": has_patient, "has_date": has_date, "results_with_value": with_value, "results_with_units": with_units}


def validate_lab_json(data: object) -> dict:
    if not isinstance(data, dict):
        raise AIError("La IA no devolvio un objeto JSON.", category="schema_invalid")
    resultados_raw = data.get("resultados") or []
    if not isinstance(resultados_raw, list):
        raise AIError("El campo resultados no es una lista.", category="schema_invalid")
    resultados = []
    dropped = 0
    for item in resultados_raw:
        normalized = _normalize_result_item(item)
        if normalized is None:
            dropped += 1
            continue
        resultados.append(normalized)
    out = {
        "paciente_nombre": _clean_value(data.get("paciente_nombre")),
        "documento_identidad": _clean_value(data.get("documento_identidad")),
        "edad": _clean_value(data.get("edad")),
        "sexo": _clean_value(data.get("sexo")),
        "laboratorio": _clean_value(data.get("laboratorio")),
        "fecha_examen": _clean_value(data.get("fecha_examen")),
        "fecha_toma_muestra": _clean_value(data.get("fecha_toma_muestra")),
        "fecha_emision": _clean_value(data.get("fecha_emision")),
        "resultados": resultados,
    }
    meta = _quality_meta(out)
    meta.update({"rows_detected": len(resultados), "rows_dropped": dropped})
    out["_meta"] = meta
    return out


def _get_price(model: str) -> dict:
    if model in MODEL_PRICES_USD_PER_MTOK:
        return MODEL_PRICES_USD_PER_MTOK[model]
    lower = model.lower()
    for key, value in MODEL_PRICES_USD_PER_MTOK.items():
        if key.lower() in lower or lower in key.lower():
            return value
    return {"input": 0.0, "output": 0.0}


def estimate_cost_usd(provider: str, model: str, prompt_tokens: int | None, output_tokens: int | None) -> float | None:
    if prompt_tokens is None and output_tokens is None:
        return None
    price = _get_price(model)
    return round(((prompt_tokens or 0) / 1_000_000) * price.get("input", 0.0) + ((output_tokens or 0) / 1_000_000) * price.get("output", 0.0), 8)


def _usage_to_dict(usage: TokenUsage) -> dict:
    return usage.__dict__.copy()


def _estimate_openai_input_tokens(pdf_b64: str) -> int:
    return max(1, int((len(pdf_b64) + len(SYSTEM_PROMPT) + len(USER_PROMPT)) / 4))


def _estimate_base64_image_tokens(images_b64: list[str]) -> int:
    total_chars = sum(len(x) for x in images_b64) + len(SYSTEM_PROMPT) + len(USER_PROMPT)
    return max(1, int(total_chars / 4))


def count_tokens_before_call(config: AIConfig, pdf_b64: str, timeout: int | None = None) -> TokenUsage:
    usage = TokenUsage(provider=config.provider, model=config.model)
    if not config.enable_token_count:
        return usage
    timeout = timeout or config.timeout_seconds
    started = time.perf_counter()
    try:
        if config.provider == "gemini":
            resp = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{config.model}:countTokens?key={config.api_key}", headers={"Content-Type": "application/json"}, payload={"contents": [{"parts": [{"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}}, {"text": SYSTEM_PROMPT.strip() + "\n\n" + USER_PROMPT}]}]}, timeout=timeout)
            usage.estimated_input_tokens = resp.get("totalTokens")
        elif config.provider == "claude":
            resp = _post("https://api.anthropic.com/v1/messages/count_tokens", headers={"Content-Type": "application/json", "x-api-key": config.api_key, "anthropic-version": "2023-06-01"}, payload={"model": config.model, "system": SYSTEM_PROMPT.strip(), "messages": [{"role": "user", "content": [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}}, {"type": "text", "text": USER_PROMPT}]}]}, timeout=timeout)
            usage.estimated_input_tokens = resp.get("input_tokens")
        elif config.provider == "openai":
            usage.estimated_input_tokens = _estimate_openai_input_tokens(pdf_b64)
        elif config.provider == "deepseek":
            usage.estimated_input_tokens = _estimate_openai_input_tokens(pdf_b64)
    except Exception as exc:
        usage.count_tokens_error = str(exc)[:300]
    finally:
        usage.count_tokens_seconds = round(time.perf_counter() - started, 2)
    return usage


def _apply_response_usage(usage: TokenUsage, resp: dict) -> TokenUsage:
    if usage.provider == "gemini":
        meta = resp.get("usageMetadata") or {}
        usage.prompt_token_count = meta.get("promptTokenCount")
        usage.candidates_token_count = meta.get("candidatesTokenCount")
        usage.total_token_count = meta.get("totalTokenCount")
        usage.cached_content_token_count = meta.get("cachedContentTokenCount")
    elif usage.provider in {"openai", "deepseek"}:
        meta = resp.get("usage") or {}
        usage.prompt_token_count = meta.get("prompt_tokens")
        usage.candidates_token_count = meta.get("completion_tokens")
        usage.total_token_count = meta.get("total_tokens")
    elif usage.provider == "claude":
        meta = resp.get("usage") or {}
        usage.prompt_token_count = meta.get("input_tokens")
        usage.candidates_token_count = meta.get("output_tokens")
        if usage.prompt_token_count is not None or usage.candidates_token_count is not None:
            usage.total_token_count = (usage.prompt_token_count or 0) + (usage.candidates_token_count or 0)
    usage.cost_estimated_usd = estimate_cost_usd(usage.provider, usage.model, usage.prompt_token_count or usage.estimated_input_tokens, usage.candidates_token_count)
    return usage


def call_claude(config: AIConfig, pdf_b64: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    usage = count_tokens_before_call(config, pdf_b64, timeout=timeout)
    resp = _post("https://api.anthropic.com/v1/messages", headers={"Content-Type": "application/json", "x-api-key": config.api_key, "anthropic-version": "2023-06-01"}, payload={"model": config.model, "max_tokens": 4096, "temperature": temperature, "system": SYSTEM_PROMPT.strip(), "messages": [{"role": "user", "content": [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}}, {"type": "text", "text": USER_PROMPT}]}]}, timeout=timeout)
    return AIResponse(resp["content"][0]["text"], _apply_response_usage(usage, resp))


def call_openai(config: AIConfig, pdf_b64: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    usage = count_tokens_before_call(config, pdf_b64, timeout=timeout)
    resp = _post("https://api.openai.com/v1/chat/completions", headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"}, payload={"model": config.model, "max_tokens": 4096, "temperature": temperature, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": SYSTEM_PROMPT.strip()}, {"role": "user", "content": [{"type": "file", "file": {"filename": "laboratorio.pdf", "file_data": f"data:application/pdf;base64,{pdf_b64}"}}, {"type": "text", "text": USER_PROMPT}]}]}, timeout=timeout)
    return AIResponse(resp["choices"][0]["message"]["content"], _apply_response_usage(usage, resp))


def call_gemini(config: AIConfig, pdf_b64: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    usage = count_tokens_before_call(config, pdf_b64, timeout=timeout)
    resp = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{config.model}:generateContent?key={config.api_key}", headers={"Content-Type": "application/json"}, payload={"system_instruction": {"parts": [{"text": SYSTEM_PROMPT.strip()}]}, "contents": [{"parts": [{"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}}, {"text": USER_PROMPT}]}], "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"}}, timeout=timeout)
    return AIResponse(resp["candidates"][0]["content"]["parts"][0]["text"], _apply_response_usage(usage, resp))


def call_deepseek(config: AIConfig, pdf_path: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    """DeepSeek no usa PDF nativo: renderiza páginas a imágenes y las envía al modelo vision. No realiza OCR local."""
    if not pdf_path:
        raise AIError("DeepSeek requiere ruta del PDF para convertir paginas a imagen.", category="config_error")
    from core.pdf_utils import pdf_pages_to_base64_images
    pages_b64 = pdf_pages_to_base64_images(pdf_path, dpi=150)
    if not pages_b64:
        raise AIError("El PDF no tiene paginas o no se pudo renderizar.", category="pdf_empty")
    usage = TokenUsage(provider=config.provider, model=config.model)
    if config.enable_token_count:
        usage.estimated_input_tokens = _estimate_base64_image_tokens(pages_b64)
    content: list[dict] = []
    for img_b64 in pages_b64:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}", "detail": "high"}})
    content.append({"type": "text", "text": USER_PROMPT})
    resp = _post("https://api.deepseek.com/v1/chat/completions", headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"}, payload={"model": config.model, "max_tokens": 4096, "temperature": temperature, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": SYSTEM_PROMPT.strip()}, {"role": "user", "content": content}]}, timeout=timeout)
    return AIResponse(resp["choices"][0]["message"]["content"], _apply_response_usage(usage, resp))


def analyze_pdf(config: AIConfig, pdf_b64: str, progress: ProgressCallback = None, pdf_path: str = "") -> AIResponse:
    if not config.api_key:
        raise ValueError("Configura tu API key antes de procesar.")
    if progress:
        if config.provider == "deepseek":
            progress(f"Enviando PDF a {config.provider} / {config.model} como imagenes por pagina...")
        else:
            progress(f"Enviando PDF a {config.provider} / {config.model}...")
    if config.provider == "claude":
        return call_claude(config, pdf_b64, timeout=config.timeout_seconds, temperature=config.temperature)
    if config.provider == "openai":
        return call_openai(config, pdf_b64, timeout=config.timeout_seconds, temperature=config.temperature)
    if config.provider == "gemini":
        return call_gemini(config, pdf_b64, timeout=config.timeout_seconds, temperature=config.temperature)
    if config.provider == "deepseek":
        return call_deepseek(config, pdf_path, timeout=config.timeout_seconds, temperature=config.temperature)
    raise ValueError(f"Proveedor no soportado: {config.provider}")


def analyze(config: AIConfig, prompt: str, progress: ProgressCallback = None) -> str:
    if not config.api_key:
        raise ValueError("Configura tu API key antes de procesar.")
    if progress:
        progress(f"Conectando a {config.provider} con modelo {config.model}...")
    if config.provider == "claude":
        resp = _post("https://api.anthropic.com/v1/messages", headers={"Content-Type": "application/json", "x-api-key": config.api_key, "anthropic-version": "2023-06-01"}, payload={"model": config.model, "max_tokens": 200, "temperature": config.temperature, "system": SYSTEM_PROMPT.strip(), "messages": [{"role": "user", "content": prompt}]}, timeout=config.timeout_seconds)
        return resp["content"][0]["text"]
    if config.provider == "openai":
        resp = _post("https://api.openai.com/v1/chat/completions", headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"}, payload={"model": config.model, "max_tokens": 200, "temperature": config.temperature, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": SYSTEM_PROMPT.strip()}, {"role": "user", "content": prompt}]}, timeout=config.timeout_seconds)
        return resp["choices"][0]["message"]["content"]
    if config.provider == "gemini":
        resp = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{config.model}:generateContent?key={config.api_key}", headers={"Content-Type": "application/json"}, payload={"system_instruction": {"parts": [{"text": SYSTEM_PROMPT.strip()}]}, "contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": config.temperature, "responseMimeType": "application/json"}}, timeout=config.timeout_seconds)
        return resp["candidates"][0]["content"]["parts"][0]["text"]
    if config.provider == "deepseek":
        resp = _post("https://api.deepseek.com/v1/chat/completions", headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"}, payload={"model": config.model, "max_tokens": 200, "temperature": config.temperature, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": SYSTEM_PROMPT.strip()}, {"role": "user", "content": prompt}]}, timeout=config.timeout_seconds)
        return resp["choices"][0]["message"]["content"]
    raise ValueError(f"Proveedor no soportado: {config.provider}")


def _compute_wait_seconds(config: AIConfig, error: AIError, attempt: int) -> int:
    if error.category == "rate_limit_429":
        if error.retry_after:
            return max(config.cooldown_on_429_seconds, int(error.retry_after))
        streak = max(1, RATE_LIMITER.current_streak())
        return max(config.cooldown_on_429_seconds, min(300, 30 * streak + 15 * attempt))
    if error.category in {"network_error", "timeout_408"}:
        # En producción conviene esperar más ante caída de internet o timeout.
        return min(90, 15 * attempt)
    if error.category in {"http_502", "http_503", "http_504"}:
        # Alta demanda/saturación temporal del modelo: backoff más conservador.
        return min(120, 30 * attempt)
    if error.category.startswith("http_"):
        return min(45, 5 * attempt)
    return min(30, 3 * attempt)


def analyze_to_json(config: AIConfig, pdf_b64: str, progress: ProgressCallback = None, pdf_path: str = "") -> dict:
    last_error: Exception | None = None
    for attempt in range(1, config.max_retries + 1):
        try:
            RATE_LIMITER.wait_for_slot(config.requests_per_minute, progress=progress)
            if progress:
                progress(f"Consulta IA intento {attempt}/{config.max_retries}...")
            ai_response = analyze_pdf(config, pdf_b64, progress=progress, pdf_path=pdf_path)
            parsed = json.loads(_extract_json_text(ai_response.text))
            validated = validate_lab_json(parsed)
            validated.setdefault("_meta", {})["token_usage"] = _usage_to_dict(ai_response.usage)
            RATE_LIMITER.reset_error_streak()
            return validated
        except AIError as e:
            last_error = e
            wait = _compute_wait_seconds(config, e, attempt)
            if e.category == "rate_limit_429":
                RATE_LIMITER.apply_cooldown(wait, progress=progress)
            if progress:
                progress(f"Intento {attempt} fallo ({e.category}). Esperando {wait}s...")
            if attempt < config.max_retries:
                time.sleep(wait + random.uniform(0.0, 0.8))
        except json.JSONDecodeError as e:
            last_error = AIError(f"JSON invalido: {e}", category="invalid_json")
            wait = min(15, 2 * attempt)
            if progress:
                progress(f"Intento {attempt}: la IA no devolvio JSON valido. Reintento en {wait}s...")
            if attempt < config.max_retries:
                time.sleep(wait + random.uniform(0.0, 0.8))
        except Exception as e:
            last_error = e
            wait = min(15, 2 * attempt)
            if progress:
                progress(f"Intento {attempt} fallo: {e}. Reintento en {wait}s...")
            if attempt < config.max_retries:
                time.sleep(wait + random.uniform(0.0, 0.8))
    if isinstance(last_error, AIError):
        raise last_error
    raise AIError(str(last_error) if last_error else "Error desconocido", category="ai_failed")


def test_connection(config: AIConfig) -> tuple[bool, str]:
    try:
        raw = analyze(config, '{"ping": "responde con JSON {\\"ok\\": true}"}')
        _extract_json_text(raw)
        return True, "Conexión correcta con la API."
    except Exception as e:
        return False, str(e)
