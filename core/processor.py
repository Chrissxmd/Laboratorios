from __future__ import annotations

import csv
import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from core.ai import AIConfig, AIError, analyze_to_json
from core.pdf_utils import OCRConfig, get_pdf_page_count, load_pdf_as_base64
from core.sairc_normalizer import normalize_ai_output
from core.cache_index import init_index, upsert_entry, is_fast_reusable, get_entry

log = logging.getLogger("lab_extractor.processor")
ProgressCallback = Optional[Callable[[dict], None]]

MAX_THREADS_BY_PROVIDER: dict[str, int] = {"gemini": 8, "openai": 4, "claude": 4, "deepseek": 2}
ABSOLUTE_MAX_THREADS = 10
APP_VERSION = "8.9"
DEFAULT_OUTPUT_FOLDER = "salida_laboratorio_gemini_sairc_v8_9"


@dataclass
class ProcessingSummary:
    total: int = 0
    success: int = 0
    errors: int = 0
    digital: int = 0
    ocr: int = 0
    skipped_success: int = 0
    threads_used: int = 1
    output_dir: str = ""
    total_prompt_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_estimated_usd: float = 0.0
    avg_seconds_per_pdf: float = 0.0
    revisar: int = 0
    ok: int = 0


def _emit(cb: ProgressCallback, **payload) -> None:
    if cb:
        cb(payload)


def _wait_if_paused_or_cancelled(pause_event: threading.Event | None, cancel_event: threading.Event | None, cb: ProgressCallback, filename: str = "", rel: str = "") -> bool:
    """Devuelve False si el usuario solicitó detener. La pausa se aplica entre PDFs o antes de llamar a la API."""
    if cancel_event is not None and cancel_event.is_set():
        return False
    notified = False
    while pause_event is not None and pause_event.is_set():
        if cancel_event is not None and cancel_event.is_set():
            return False
        if not notified:
            _emit(cb, stage="paused", filename=filename, ruta_relativa=rel, message=f"Pausado. Se retomará desde cache al continuar: {rel or filename}")
            notified = True
        time.sleep(0.25)
    if notified:
        _emit(cb, stage="resumed", filename=filename, ruta_relativa=rel, message="Proceso reanudado.")
    return True


def safe_max_threads(provider: str) -> int:
    return min(MAX_THREADS_BY_PROVIDER.get(provider.lower(), 2), ABSOLUTE_MAX_THREADS)


def _safe_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, AIError):
        return exc.category, str(exc)
    if isinstance(exc, FileNotFoundError):
        return "file_not_found", str(exc)
    if isinstance(exc, PermissionError):
        return "permission_error", str(exc)
    if isinstance(exc, RuntimeError):
        return "runtime_error", str(exc)
    if isinstance(exc, ValueError):
        return "value_error", str(exc)
    return "unexpected_error", str(exc)


TEMPORARY_ERROR_TYPES = {
    "http_500", "http_502", "http_503", "http_504",
    "timeout_408", "rate_limit_429", "network_error", "ai_failed",
}


def _is_temporary_error(error_type: str | None, error_msg: str | None = None) -> bool:
    et = (error_type or "").lower()
    msg = (error_msg or "").lower()
    if et in TEMPORARY_ERROR_TYPES:
        return True
    temporary_markers = [
        "tempor", "timeout", "timed out", "connection", "network", "unreachable",
        "high demand", "overloaded", "unavailable", "503", "502", "504", "429",
    ]
    return any(m in et or m in msg for m in temporary_markers)


def _temporary_errors_from_state(state_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for meta_path in sorted(state_dir.glob("*.meta.json")):
        try:
            meta = _read_json(meta_path)
            if meta.get("status") == "error" and _is_temporary_error(meta.get("error_type"), meta.get("error")):
                rows.append({**meta, "_meta_path": str(meta_path)})
        except Exception:
            continue
    return rows


def _pdf_from_meta(meta: dict, input_dir: Path) -> Path | None:
    rel = meta.get("ruta_relativa") or meta.get("filename")
    if not rel:
        return None
    path = input_dir / rel
    return path if path.exists() else None


def _write_csv_dicts(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in headers and not k.startswith("_"):
                headers.append(k)
    if not headers:
        headers = ["sin_datos"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in headers})


def _write_retry_outputs(out_dir: Path, state_dir: Path) -> list[dict]:
    errors = _temporary_errors_from_state(state_dir)
    queue = []
    for m in errors:
        queue.append({
            "archivo": m.get("filename"),
            "ruta_relativa": m.get("ruta_relativa"),
            "carpeta_origen": m.get("carpeta_origen"),
            "error_type": m.get("error_type"),
            "error": m.get("error"),
            "updated_at": m.get("updated_at"),
            "reprocesar_si_no": "SI",
            "recomendacion": "Reprocesar automáticamente o ejecutar reproceso de errores temporales.",
        })
    _safe_write_json(out_dir / "retry_queue.json", {"updated_at": datetime.now().isoformat(timespec="seconds"), "count": len(queue), "items": queue})
    _write_csv_dicts(out_dir / "errores_reprocesables.csv", queue)
    return queue


def _token_usage(data: dict) -> dict:
    return ((data.get("_meta") or {}).get("token_usage") or {})


def _quality(data: dict) -> dict:
    meta = data.get("_meta") or {}
    return {
        "quality_score": meta.get("quality_score"),
        "quality_level": meta.get("quality_level"),
        "rows_detected": meta.get("rows_detected"),
        "rows_dropped": meta.get("rows_dropped"),
    }


def _sha12(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def _quick_file_info(pdf_path: Path, input_dir: Path) -> dict:
    st = pdf_path.stat()
    rel = pdf_path.relative_to(input_dir).as_posix()
    carpeta = str(Path(rel).parent).replace(".", "")
    return {
        "ruta_relativa": rel,
        "filename": pdf_path.name,
        "carpeta_origen": carpeta,
        "size_bytes": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
    }


def _index_entry_from_meta(meta: dict, raw_path: Path | None, norm_path: Path | None, meta_path: Path, pdf_path: Path | None = None, input_dir: Path | None = None) -> dict:
    entry = {
        "ruta_relativa": meta.get("ruta_relativa"),
        "filename": meta.get("filename"),
        "carpeta_origen": meta.get("carpeta_origen"),
        "cache_stem": meta.get("cache_stem"),
        "raw_json": str(raw_path) if raw_path else None,
        "norm_json": str(norm_path) if norm_path else None,
        "meta_json": str(meta_path),
        "status": meta.get("status"),
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "updated_at": meta.get("updated_at"),
        "error_type": meta.get("error_type"),
        "error": meta.get("error"),
    }
    if pdf_path is not None and input_dir is not None and pdf_path.exists():
        entry.update({k: v for k, v in _quick_file_info(pdf_path, input_dir).items() if k in {"size_bytes", "mtime_ns"}})
    else:
        entry["size_bytes"] = meta.get("size_bytes")
        entry["mtime_ns"] = meta.get("mtime_ns")
    return entry


def _cache_stem(pdf_path: Path, input_dir: Path) -> tuple[str, str, str]:
    rel = pdf_path.relative_to(input_dir).as_posix()
    digest = _sha12(pdf_path)
    safe_rel = rel.replace("/", "__").replace("\\", "__")
    stem = f"{Path(safe_rel).stem}.{digest}"
    carpeta = str(Path(rel).parent).replace(".", "")
    return stem, rel, carpeta


def _row_archivo_from_meta(meta: dict, raw: dict | None, norm: dict | None) -> dict:
    usage = _token_usage(raw or {})
    q = _quality(raw or {})
    cab = (norm or {}).get("cabecera") or {}
    return {
        "ruta_relativa": meta.get("ruta_relativa"),
        "archivo": meta.get("filename"),
        "carpeta_origen": meta.get("carpeta_origen"),
        "status": meta.get("status"),
        "estado_archivo": cab.get("estado_archivo"),
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "pages": meta.get("pages"),
        "file_size_mb": meta.get("file_size_mb"),
        "seconds": meta.get("seconds"),
        "paciente": cab.get("paciente"),
        "documento_archivo_pdf": cab.get("documento_archivo_pdf"),
        "documento_identidad": cab.get("documento_identidad"),
        "coincidencia_documento": cab.get("coincidencia_documento"),
        "estado_identidad": cab.get("estado_identidad"),
        "requiere_verificacion_identidad": cab.get("requiere_verificacion_identidad"),
        "requiere_verificacion_resultados": cab.get("requiere_verificacion_resultados"),
        "requiere_verificacion_humana": cab.get("requiere_verificacion_humana"),
        "motivo_identidad": cab.get("motivo_identidad"),
        "laboratorio": cab.get("laboratorio"),
        "fecha_toma_muestra": cab.get("fecha_toma_muestra"),
        "fecha_emision": cab.get("fecha_emision"),
        "resultados_extraidos": cab.get("resultados_extraidos"),
        "resultados_normalizados": cab.get("resultados_normalizados"),
        "resultados_revisar": cab.get("resultados_revisar"),
        "faltantes_basicos": cab.get("faltantes_basicos"),
        **q,
        "tokens_estimados_entrada": usage.get("estimated_input_tokens"),
        "prompt_token_count": usage.get("prompt_token_count"),
        "candidates_token_count": usage.get("candidates_token_count"),
        "total_token_count": usage.get("total_token_count"),
        "costo_estimado_usd": usage.get("cost_estimated_usd"),
        "error_type": meta.get("error_type"),
        "error": meta.get("error"),
    }


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _process_single_pdf(pdf_path: Path, input_dir: Path, idx: int, total: int, ai_config: AIConfig, raw_dir: Path, norm_dir: Path, state_dir: Path, progress_cb: ProgressCallback, log_jsonl: Path, pause_event: threading.Event | None = None, cancel_event: threading.Event | None = None) -> dict:
    stem, rel, carpeta = _cache_stem(pdf_path, input_dir)
    name = pdf_path.name
    meta_path = state_dir / f"{stem}.meta.json"
    raw_path = raw_dir / f"{stem}.json"
    norm_path = norm_dir / f"{stem}.normalizado.json"

    def emit(**kw):
        _emit(progress_cb, filename=name, ruta_relativa=rel, current=idx, total=total, **kw)

    started = time.perf_counter()
    try:
        if not _wait_if_paused_or_cancelled(pause_event, cancel_event, progress_cb, name, rel):
            emit(stage="cancelled_file", message=f"[{idx}/{total}] ⏹ Omitido por detención: {rel}")
            return {"ok": False, "cancelled": True, "skipped": False, "meta": None, "raw": None, "norm": None}
        if meta_path.exists() and raw_path.exists() and norm_path.exists():
            meta = _read_json(meta_path)
            if meta.get("status") == "success":
                emit(stage="skip_file", message=f"[{idx}/{total}] ↷ Reutilizando cache IA: {rel}")
                return {"ok": True, "skipped": True, "meta": meta_path, "raw": raw_path, "norm": norm_path}

        emit(stage="start_file", message=f"[{idx}/{total}] Iniciando {rel}")
        t_pdf = time.perf_counter()
        pages = get_pdf_page_count(str(pdf_path))
        size_mb = round(pdf_path.stat().st_size / (1024 * 1024), 3)
        emit(stage="extract", message=f"Cargando PDF ({pages or 'sin conteo'} pág., {size_mb} MB): {rel}")
        pdf_b64 = load_pdf_as_base64(str(pdf_path))
        pdf_load_seconds = round(time.perf_counter() - t_pdf, 2)
        if not _wait_if_paused_or_cancelled(pause_event, cancel_event, progress_cb, name, rel):
            emit(stage="cancelled_file", message=f"[{idx}/{total}] ⏹ Omitido por detención antes de IA: {rel}")
            return {"ok": False, "cancelled": True, "skipped": False, "meta": None, "raw": None, "norm": None}
        mode = "api_vision_images" if ai_config.provider == "deepseek" else "api_native_pdf"

        def ai_progress(msg: str):
            emit(stage="ai_detail", message=f"{name}: {msg}")
            log.debug("%s: %s", name, msg)

        t_ai = time.perf_counter()
        raw_data = analyze_to_json(ai_config, pdf_b64, progress=ai_progress, pdf_path=str(pdf_path))
        ai_seconds = round(time.perf_counter() - t_ai, 2)
        raw_data.setdefault("_source", {})
        raw_data["_source"].update({"ruta_relativa": rel, "archivo": name, "carpeta_origen": carpeta, "cache_stem": stem})
        t_norm = time.perf_counter()
        norm_data = normalize_ai_output(raw_data, ruta_relativa=rel, carpeta_origen=carpeta)
        normalize_seconds = round(time.perf_counter() - t_norm, 2)
        _safe_write_json(raw_path, raw_data)
        _safe_write_json(norm_path, norm_data)
        usage = _token_usage(raw_data)
        seconds = round(time.perf_counter() - started, 2)
        qinfo = _quick_file_info(pdf_path, input_dir)
        meta = {
            "filename": name,
            "ruta_relativa": rel,
            "carpeta_origen": carpeta,
            "cache_stem": stem,
            "size_bytes": qinfo.get("size_bytes"),
            "mtime_ns": qinfo.get("mtime_ns"),
            "status": "success",
            "mode": mode,
            "provider": ai_config.provider,
            "model": ai_config.model,
            "pages": pages,
            "file_size_mb": size_mb,
            "pdf_load_seconds": pdf_load_seconds,
            "ai_seconds": ai_seconds,
            "normalize_seconds": normalize_seconds,
            "seconds": seconds,
            "rows": len(raw_data.get("resultados") or []),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "error_type": None,
            "error": None,
        }
        _safe_write_json(meta_path, meta)
        _append_jsonl(log_jsonl, {"event": "success", **meta, "token_usage": usage})
        emit(stage="done_file", message=f"[{idx}/{total}] ✓ {rel} ({len(raw_data.get('resultados') or [])} filas IA, USD {usage.get('cost_estimated_usd') or 0})")
        return {"ok": True, "skipped": False, "meta": meta_path, "raw": raw_path, "norm": norm_path}
    except Exception as exc:
        error_type, error_msg = _normalize_error(exc)
        qinfo = _quick_file_info(pdf_path, input_dir) if pdf_path.exists() else {}
        temporary = _is_temporary_error(error_type, error_msg)
        meta = {
            "filename": name, "ruta_relativa": rel, "carpeta_origen": carpeta, "cache_stem": stem,
            "size_bytes": qinfo.get("size_bytes"), "mtime_ns": qinfo.get("mtime_ns"),
            "status": "error", "mode": None, "provider": ai_config.provider, "model": ai_config.model,
            "pages": None, "file_size_mb": None, "seconds": round(time.perf_counter() - started, 2),
            "rows": 0, "updated_at": datetime.now().isoformat(timespec="seconds"),
            "error_type": error_type, "error": error_msg,
            "temporary_error": temporary,
            "reprocesable": temporary,
        }
        _safe_write_json(meta_path, meta)
        _append_jsonl(log_jsonl, {"event": "error", **meta})
        log.error("ERROR %s [%s]: %s", rel, error_type, error_msg)
        emit(stage="error_file", message=f"[{idx}/{total}] ✗ {rel}: {error_type} - {error_msg}")
        return {"ok": False, "skipped": False, "meta": meta_path, "raw": None, "norm": None}


def _write_sheet(wb, title: str, rows: list[dict]) -> None:
    ws = wb.active if wb.active.title == "Sheet" else wb.create_sheet(title)
    ws.title = title[:31]
    if not rows:
        ws.append(["sin_datos"])
        return
    headers: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in headers:
                headers.append(k)
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h) for h in headers])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col in ws.columns:
        try:
            max_len = max(len(str(c.value)) if c.value is not None else 0 for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 2, 10), 45)
        except Exception:
            pass


def _write_excel(output_dir: Path, resumen_rows: list[dict], control_rows: list[dict], normalizados: list[dict], sairc_rows: list[dict], archivo_rows: list[dict], pendientes: list[dict], raw_rows: list[dict], costos_rows: list[dict], error_rows: list[dict]) -> None:
    try:
        from openpyxl import Workbook
        wb = Workbook()
        sairc_cargable, sairc_revision, sairc_no_cargable = _split_sairc_rows(sairc_rows)
        control_identidad = [{k: r.get(k) for k in [
            "ruta_relativa", "archivo", "carpeta_origen", "paciente", "documento_archivo_pdf", "documento_archivo_normalizado",
            "documento_identidad", "documento_pdf_normalizado", "coincidencia_documento", "estado_identidad",
            "requiere_verificacion_identidad", "requiere_verificacion_resultados", "requiere_verificacion_humana",
            "motivo_identidad", "documentos_detectados", "puede_cargarse_sairc",
        ]} for r in control_rows]
        alertas_calidad = []
        for r in pendientes:
            alertas_calidad.append(r)
        for r in normalizados:
            if str(r.get("estado_control") or "").upper() == "OK_CON_REGLA" or str(r.get("estado_produccion") or "").upper() == "OK_CON_ALERTA_CLINICA":
                alertas_calidad.append(r)
        resumen_ipress = _build_resumen_ipress(archivo_rows)
        _write_sheet(wb, "Resumen", resumen_rows)
        _write_sheet(wb, "Resumen_IPRESS", resumen_ipress)
        _write_sheet(wb, "Control_Identidad", control_identidad)
        _write_sheet(wb, "Control_Calidad", control_rows)
        _write_sheet(wb, "SAIRC_Cargable", sairc_cargable)
        _write_sheet(wb, "SAIRC_Revision", sairc_revision)
        _write_sheet(wb, "SAIRC_No_Cargable", sairc_no_cargable)
        _write_sheet(wb, "SAIRC_Formulario2", sairc_rows)
        _write_sheet(wb, "Resultados_Normalizados", normalizados)
        _write_sheet(wb, "Archivos", archivo_rows)
        pendientes_alta = [r for r in pendientes if str(r.get("severidad") or "").upper() == "ALTA" or "identidad" in str(r.get("motivo") or "").lower()]
        _write_sheet(wb, "Pendientes_Alta", pendientes_alta)
        _write_sheet(wb, "Pendientes_Revision", pendientes)
        _write_sheet(wb, "Alertas_Calidad", alertas_calidad)
        _write_sheet(wb, "Raw_Gemini", raw_rows)
        _write_sheet(wb, "Costos_Latencia", costos_rows)
        _write_sheet(wb, "Errores", error_rows)
        wb.save(output_dir / "resultados_laboratorio_sairc.xlsx")
    except Exception as exc:
        log.warning("No se pudo generar Excel: %s", exc)


def _build_resumen_ipress(archivo_rows: list[dict]) -> list[dict]:
    acc: dict[str, dict] = {}
    for r in archivo_rows:
        key = r.get("carpeta_origen") or "(raiz)"
        row = acc.setdefault(key, {
            "carpeta_origen": key, "total_archivos": 0, "ok_cargable": 0, "revision": 0,
            "no_cargable_identidad": 0, "sin_doc_pdf": 0, "errores_tecnicos": 0,
            "costo_estimado_usd": 0.0, "segundos_total": 0.0,
        })
        row["total_archivos"] += 1
        estado = str(r.get("estado_archivo") or "").upper()
        est_id = str(r.get("estado_identidad") or "").upper()
        if estado in {"OK_CARGABLE", "OK_CON_ALERTA_CLINICA", "OK", "OK_CON_REGLA"}:
            row["ok_cargable"] += 1
        elif estado == "NO_CARGABLE_IDENTIDAD" or est_id == "NO_CARGABLE_IDENTIDAD":
            row["no_cargable_identidad"] += 1
        elif "SIN_DOCUMENTO" in est_id or str(r.get("coincidencia_documento") or "").upper() == "SIN_DOC_OCR":
            row["sin_doc_pdf"] += 1
        elif estado or r.get("status") == "success":
            row["revision"] += 1
        else:
            row["errores_tecnicos"] += 1
        try:
            row["costo_estimado_usd"] += float(r.get("costo_estimado_usd") or 0)
        except Exception:
            pass
        try:
            row["segundos_total"] += float(r.get("seconds") or 0)
        except Exception:
            pass
    out = []
    for row in acc.values():
        total = row["total_archivos"] or 1
        row["costo_estimado_usd"] = round(row["costo_estimado_usd"], 6)
        row["segundos_promedio"] = round(row["segundos_total"] / total, 2)
        row["segundos_total"] = round(row["segundos_total"], 2)
        out.append(row)
    return sorted(out, key=lambda x: str(x.get("carpeta_origen")))


def _write_csv(path: Path, rows: list[dict]) -> None:
    headers: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in headers:
                headers.append(k)
    if not headers:
        headers = ["sin_datos"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _split_sairc_rows(sairc_rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Devuelve filas cargables, en revisión y no cargables.

    Regla de seguridad: el CSV histórico sairc_formulario2.csv se mantiene,
    pero desde v8.8 final contiene SOLO filas cargables. El archivo con todo
    se llama sairc_todos_con_estado.csv.
    """
    cargable: list[dict] = []
    revision: list[dict] = []
    no_cargable: list[dict] = []
    for r in sairc_rows:
        estado = str(r.get("estado_archivo") or "").upper()
        puede = str(r.get("puede_cargarse_sairc") or "").upper()
        if puede == "SI" and estado in {"OK_CARGABLE", "OK_CON_ALERTA_CLINICA", "OK", "OK_CON_REGLA"}:
            cargable.append(r)
        elif estado == "SAIRC_REVISION":
            revision.append(r)
        else:
            no_cargable.append(r)
    return cargable, revision, no_cargable


def _write_sairc_csvs(output_dir: Path, sairc_rows: list[dict]) -> None:
    cargable, revision, no_cargable = _split_sairc_rows(sairc_rows)
    _write_csv(output_dir / "sairc_formulario2.csv", cargable)  # compatibilidad: solo cargables
    _write_csv(output_dir / "sairc_cargable.csv", cargable)
    _write_csv(output_dir / "sairc_revision.csv", revision)
    _write_csv(output_dir / "sairc_no_cargable.csv", no_cargable)
    _write_csv(output_dir / "sairc_todos_con_estado.csv", sairc_rows)


def _avg_seconds(costos_rows: list[dict]) -> float:
    vals = []
    for r in costos_rows:
        try:
            v = float(r.get("seconds") or 0)
            if v > 0:
                vals.append(v)
        except Exception:
            pass
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def _collect_outputs(pdf_files: list[Path], input_dir: Path, raw_dir: Path, norm_dir: Path, state_dir: Path, output_dir: Path, ai_config: AIConfig) -> ProcessingSummary:
    summary = ProcessingSummary(total=len(pdf_files))
    archivo_rows: list[dict] = []
    control_rows: list[dict] = []
    normalizados: list[dict] = []
    sairc_rows: list[dict] = []
    pendientes: list[dict] = []
    raw_rows: list[dict] = []
    costos_rows: list[dict] = []
    error_rows: list[dict] = []

    for pdf_path in pdf_files:
        stem, rel, carpeta = _cache_stem(pdf_path, input_dir)
        meta_path = state_dir / f"{stem}.meta.json"
        raw_path = raw_dir / f"{stem}.json"
        norm_path = norm_dir / f"{stem}.normalizado.json"
        if not meta_path.exists():
            continue
        meta = _read_json(meta_path)
        raw = _read_json(raw_path) if raw_path.exists() and meta.get("status") == "success" else None
        norm = _read_json(norm_path) if norm_path.exists() and meta.get("status") == "success" else None
        archivo_rows.append(_row_archivo_from_meta(meta, raw, norm))
        if meta.get("status") != "success":
            summary.errors += 1
            error_rows.append({"ruta_relativa": rel, "archivo": pdf_path.name, "error_tipo": meta.get("error_type"), "error": meta.get("error")})
            continue
        summary.success += 1
        summary.digital += 1
        cab = (norm or {}).get("cabecera") or {}
        if str(cab.get("estado_archivo") or "").upper() in {"OK", "OK_CON_REGLA", "OK_CARGABLE", "OK_CON_ALERTA_CLINICA"}:
            summary.ok += 1
        else:
            summary.revisar += 1
        usage = _token_usage(raw or {})
        summary.total_prompt_tokens += int(usage.get("prompt_token_count") or usage.get("estimated_input_tokens") or 0)
        summary.total_output_tokens += int(usage.get("candidates_token_count") or 0)
        summary.total_tokens += int(usage.get("total_token_count") or 0)
        summary.total_cost_estimated_usd += float(usage.get("cost_estimated_usd") or 0.0)
        control_rows.append(cab)
        sairc_rows.append((norm or {}).get("sairc") or {})
        for r in (norm or {}).get("resultados_normalizados") or []:
            normalizados.append({**{k: cab.get(k) for k in ["ruta_relativa", "paciente", "documento_archivo_pdf", "documento_identidad", "coincidencia_documento", "estado_identidad", "puede_cargarse_sairc", "laboratorio"]}, **r})
        pendientes.extend((norm or {}).get("pendientes") or [])
        raw_rows.append({
            "ruta_relativa": rel,
            "paciente": (raw or {}).get("paciente_nombre"),
            "documento_identidad": (raw or {}).get("documento_identidad"),
            "laboratorio": (raw or {}).get("laboratorio"),
            "resultados_raw": len((raw or {}).get("resultados") or []),
            "json_ai_raw": raw_path.name,
            "json_ai_normalizado": norm_path.name,
        })
        costos_rows.append({
            "ruta_relativa": rel,
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "pages": meta.get("pages"),
            "file_size_mb": meta.get("file_size_mb"),
            "seconds": meta.get("seconds"),
            "pdf_load_seconds": meta.get("pdf_load_seconds"),
            "ai_seconds": meta.get("ai_seconds"),
            "normalize_seconds": meta.get("normalize_seconds"),
            "rpm_configurado": ai_config.requests_per_minute,
            "count_tokens_activo": ai_config.enable_token_count,
            "count_tokens_seconds": usage.get("count_tokens_seconds"),
            "tokens_estimados_entrada": usage.get("estimated_input_tokens"),
            "prompt_token_count": usage.get("prompt_token_count"),
            "candidates_token_count": usage.get("candidates_token_count"),
            "total_token_count": usage.get("total_token_count"),
            "costo_estimado_usd": usage.get("cost_estimated_usd"),
        })

    summary.avg_seconds_per_pdf = _avg_seconds(costos_rows)

    resumen_rows = [{
        "version": APP_VERSION,
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        "total_pdf": len(pdf_files),
        "procesados_ok": summary.success,
        "errores": summary.errors,
        "archivos_ok_o_alerta": summary.ok,
        "archivos_revisar": summary.revisar,
        "resultados_normalizados": len(normalizados),
        "pendientes_revision": len(pendientes),
        "provider": ai_config.provider,
        "model": ai_config.model,
        "total_tokens": summary.total_tokens,
        "costo_estimado_usd": round(summary.total_cost_estimated_usd, 6),
        "promedio_segundos_pdf": summary.avg_seconds_per_pdf,
    }]

    _write_csv(output_dir / "resultados_normalizados.csv", normalizados)
    _write_sairc_csvs(output_dir, sairc_rows)
    _write_csv(output_dir / "pendientes_revision.csv", pendientes)
    _write_csv(output_dir / "archivos.csv", archivo_rows)
    _write_csv(output_dir / "errores_laboratorio.csv", error_rows)
    _write_excel(output_dir, resumen_rows, control_rows, normalizados, sairc_rows, archivo_rows, pendientes, raw_rows, costos_rows, error_rows)
    return summary




def _rebuild_index_from_state(cache_index_path: Path, input_dir: Path, raw_dir: Path, norm_dir: Path, state_dir: Path) -> int:
    """Reconstruye índice SQLite desde estado_pdf/*.meta.json sin llamar a IA."""
    init_index(cache_index_path)
    count = 0
    for meta_path in state_dir.glob("*.meta.json"):
        try:
            meta = _read_json(meta_path)
            rel = meta.get("ruta_relativa")
            if not rel:
                continue
            pdf_path = input_dir / rel
            raw_path = raw_dir / f"{meta.get('cache_stem')}.json" if meta.get("cache_stem") else None
            norm_path = norm_dir / f"{meta.get('cache_stem')}.normalizado.json" if meta.get("cache_stem") else None
            entry = _index_entry_from_meta(meta, raw_path, norm_path, meta_path, pdf_path if pdf_path.exists() else None, input_dir)
            upsert_entry(cache_index_path, entry)
            count += 1
        except Exception as exc:
            log.debug("No se pudo indexar %s: %s", meta_path, exc)
    return count


def _collect_outputs_fast(pdf_files: list[Path], input_dir: Path, cache_index_path: Path, output_dir: Path, ai_config: AIConfig) -> ProcessingSummary:
    """Colecta resultados usando SQLite, evitando calcular hash de todos los PDFs."""
    summary = ProcessingSummary(total=len(pdf_files))
    archivo_rows: list[dict] = []
    control_rows: list[dict] = []
    normalizados: list[dict] = []
    sairc_rows: list[dict] = []
    pendientes: list[dict] = []
    raw_rows: list[dict] = []
    costos_rows: list[dict] = []
    error_rows: list[dict] = []

    for pdf_path in pdf_files:
        qinfo = _quick_file_info(pdf_path, input_dir)
        rel = qinfo["ruta_relativa"]
        row = get_entry(cache_index_path, rel)
        if not row:
            continue
        meta_path = Path(row.get("meta_json") or "")
        raw_path = Path(row.get("raw_json") or "") if row.get("raw_json") else None
        norm_path = Path(row.get("norm_json") or "") if row.get("norm_json") else None
        if not meta_path.exists():
            continue
        meta = _read_json(meta_path)
        raw = _read_json(raw_path) if raw_path and raw_path.exists() and meta.get("status") == "success" else None
        norm = _read_json(norm_path) if norm_path and norm_path.exists() and meta.get("status") == "success" else None
        archivo_rows.append(_row_archivo_from_meta(meta, raw, norm))
        if meta.get("status") != "success":
            summary.errors += 1
            error_rows.append({"ruta_relativa": rel, "archivo": pdf_path.name, "error_tipo": meta.get("error_type"), "error": meta.get("error")})
            continue
        summary.success += 1
        summary.digital += 1
        cab = (norm or {}).get("cabecera") or {}
        if str(cab.get("estado_archivo") or "").upper() in {"OK", "OK_CON_REGLA", "OK_CARGABLE", "OK_CON_ALERTA_CLINICA"}:
            summary.ok += 1
        else:
            summary.revisar += 1
        usage = _token_usage(raw or {})
        summary.total_prompt_tokens += int(usage.get("prompt_token_count") or usage.get("estimated_input_tokens") or 0)
        summary.total_output_tokens += int(usage.get("candidates_token_count") or 0)
        summary.total_tokens += int(usage.get("total_token_count") or 0)
        summary.total_cost_estimated_usd += float(usage.get("cost_estimated_usd") or 0.0)
        control_rows.append(cab)
        sairc_rows.append((norm or {}).get("sairc") or {})
        for r in (norm or {}).get("resultados_normalizados") or []:
            normalizados.append({**{k: cab.get(k) for k in ["ruta_relativa", "paciente", "documento_archivo_pdf", "documento_identidad", "coincidencia_documento", "estado_identidad", "puede_cargarse_sairc", "laboratorio"]}, **r})
        pendientes.extend((norm or {}).get("pendientes") or [])
        raw_rows.append({
            "ruta_relativa": rel,
            "paciente": (raw or {}).get("paciente_nombre"),
            "documento_archivo_pdf": cab.get("documento_archivo_pdf"),
            "documento_identidad": (raw or {}).get("documento_identidad"),
            "coincidencia_documento": cab.get("coincidencia_documento"),
            "laboratorio": (raw or {}).get("laboratorio"),
            "resultados_raw": len((raw or {}).get("resultados") or []),
            "json_ai_raw": raw_path.name if raw_path else None,
            "json_ai_normalizado": norm_path.name if norm_path else None,
        })
        costos_rows.append({
            "ruta_relativa": rel,
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "pages": meta.get("pages"),
            "file_size_mb": meta.get("file_size_mb"),
            "seconds": meta.get("seconds"),
            "pdf_load_seconds": meta.get("pdf_load_seconds"),
            "ai_seconds": meta.get("ai_seconds"),
            "normalize_seconds": meta.get("normalize_seconds"),
            "rpm_configurado": ai_config.requests_per_minute,
            "count_tokens_activo": ai_config.enable_token_count,
            "count_tokens_seconds": usage.get("count_tokens_seconds"),
            "tokens_estimados_entrada": usage.get("estimated_input_tokens"),
            "prompt_token_count": usage.get("prompt_token_count"),
            "candidates_token_count": usage.get("candidates_token_count"),
            "total_token_count": usage.get("total_token_count"),
            "costo_estimado_usd": usage.get("cost_estimated_usd"),
        })

    summary.avg_seconds_per_pdf = _avg_seconds(costos_rows)

    resumen_rows = [{
        "version": APP_VERSION,
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        "total_pdf": len(pdf_files),
        "procesados_ok": summary.success,
        "errores": summary.errors,
        "archivos_ok_o_alerta": summary.ok,
        "archivos_revisar": summary.revisar,
        "resultados_normalizados": len(normalizados),
        "pendientes_revision": len(pendientes),
        "provider": ai_config.provider,
        "model": ai_config.model,
        "total_tokens": summary.total_tokens,
        "costo_estimado_usd": round(summary.total_cost_estimated_usd, 6),
        "promedio_segundos_pdf": summary.avg_seconds_per_pdf,
        "cache_index": str(cache_index_path),
    }]

    _write_csv(output_dir / "resultados_normalizados.csv", normalizados)
    _write_sairc_csvs(output_dir, sairc_rows)
    _write_csv(output_dir / "pendientes_revision.csv", pendientes)
    _write_csv(output_dir / "archivos.csv", archivo_rows)
    _write_csv(output_dir / "errores_laboratorio.csv", error_rows)
    _write_excel(output_dir, resumen_rows, control_rows, normalizados, sairc_rows, archivo_rows, pendientes, raw_rows, costos_rows, error_rows)
    return summary


def process_folder(
    folder_path: str,
    ai_config: AIConfig,
    ocr_config: OCRConfig,
    progress_cb: ProgressCallback = None,
    threads: int = 1,
    output_dir: str | None = None,
    resume_fast: bool = True,
    rebuild_index: bool = False,
    skip_cache_validation: bool = False,
    pause_event: threading.Event | None = None,
    cancel_event: threading.Event | None = None,
) -> ProcessingSummary:
    provider_max = safe_max_threads(ai_config.provider)
    threads = max(1, min(int(threads), provider_max))
    input_dir = Path(folder_path)
    if not input_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta: {input_dir}")
    pdf_files = sorted(input_dir.rglob("*.pdf"))
    out_dir = Path(output_dir) if output_dir else input_dir / DEFAULT_OUTPUT_FOLDER
    raw_dir = out_dir / "cache_ai" / "json_ai_raw"
    norm_dir = out_dir / "cache_ai" / "json_ai_normalizado"
    state_dir = out_dir / "estado_pdf"
    cache_index_path = out_dir / "cache_ai" / "cache_index.sqlite"
    for d in [out_dir, raw_dir, norm_dir, state_dir, cache_index_path.parent]:
        d.mkdir(parents=True, exist_ok=True)
    init_index(cache_index_path)

    run_log = out_dir / "process.log"
    fh = logging.FileHandler(run_log, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(fh); log.setLevel(logging.DEBUG)
    log_jsonl = out_dir / "process.jsonl"
    log.info("==== NUEVA EJECUCION v%s GEMINI/IA DIRECTA + SAIRC + CACHE RAPIDO ====", APP_VERSION)
    log.info("Inicio — %d PDFs, %d hilos, proveedor=%s, modelo=%s", len(pdf_files), threads, ai_config.provider, ai_config.model)

    if rebuild_index:
        rebuilt = _rebuild_index_from_state(cache_index_path, input_dir, raw_dir, norm_dir, state_dir)
        _emit(progress_cb, stage="rebuild_index", message=f"Índice reconstruido desde estado_pdf: {rebuilt} registros", percent=0, total=len(pdf_files), current=0)

    _emit(progress_cb, stage="scan", message=f"Se encontraron {len(pdf_files)} PDFs incluyendo subcarpetas. Salida: {out_dir}", percent=0, total=len(pdf_files), current=0)
    if not pdf_files:
        log.removeHandler(fh); fh.close()
        return ProcessingSummary(total=0, threads_used=threads, output_dir=str(out_dir))

    to_process: list[tuple[int, Path]] = []
    skipped_success = 0
    if resume_fast:
        for idx, pdf_path in enumerate(pdf_files, start=1):
            q = _quick_file_info(pdf_path, input_dir)
            reusable = is_fast_reusable(
                cache_index_path, q["ruta_relativa"], q["size_bytes"], q["mtime_ns"],
                ai_config.provider, ai_config.model, validate_files=not skip_cache_validation,
            )
            if reusable:
                skipped_success += 1
            else:
                to_process.append((idx, pdf_path))
        _emit(progress_cb, stage="resume_fast", message=f"Cache rápido reutilizado: {skipped_success}. Pendientes IA: {len(to_process)}", percent=0, total=len(pdf_files), current=0)
    else:
        to_process = list(enumerate(pdf_files, start=1))

    completed = skipped_success
    completed_lock = threading.Lock()

    def wrap_progress(payload: dict) -> None:
        nonlocal completed
        if payload.get("stage") in {"done_file", "error_file", "skip_file", "cancelled_file"}:
            with completed_lock:
                completed += 1
                pct = int((completed / len(pdf_files)) * 100)
            payload = {**payload, "completed": completed, "percent": pct, "skipped": payload.get("stage") == "skip_file"}
        _emit(progress_cb, **payload)

    def _run_batch(batch_items: list[tuple[int, Path]], workers: int, progress_func: Callable[[dict], None]) -> None:
        nonlocal skipped_success
        if not batch_items:
            return
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(_process_single_pdf, pdf_path, input_dir, idx, len(pdf_files), ai_config, raw_dir, norm_dir, state_dir, progress_func, log_jsonl, pause_event, cancel_event): pdf_path
                for idx, pdf_path in batch_items
            }
            for future in as_completed(futures):
                result = future.result()
                if result.get("cancelled"):
                    continue
                meta_path = result.get("meta")
                try:
                    if meta_path:
                        meta = _read_json(Path(meta_path))
                        cache_stem = meta.get("cache_stem")
                        pdf_path = futures[future]
                        raw_path = raw_dir / f"{cache_stem}.json" if cache_stem else None
                        norm_path = norm_dir / f"{cache_stem}.normalizado.json" if cache_stem else None
                        upsert_entry(cache_index_path, _index_entry_from_meta(meta, raw_path, norm_path, Path(meta_path), pdf_path, input_dir))
                except Exception as exc:
                    log.debug("No se pudo actualizar índice para %s: %s", futures.get(future), exc)
                if result.get("skipped"):
                    skipped_success += 1

    _run_batch(to_process, threads, wrap_progress)

    # Reproceso automático de errores temporales: 503, 429, timeout y problemas de red.
    # No incrementa el contador global de progreso para no superar el 100%; solo actualiza log y estado.
    def retry_progress(payload: dict) -> None:
        stage = payload.get("stage")
        new_stage = {
            "done_file": "retry_done_file",
            "error_file": "retry_error_file",
            "start_file": "retry_start_file",
            "extract": "retry_extract",
            "ai_detail": "retry_ai_detail",
        }.get(stage, stage)
        payload = {**payload, "stage": new_stage, "percent": min(99, int((completed / len(pdf_files)) * 100) if pdf_files else 0)}
        _emit(progress_cb, **payload)

    retry_rounds_done = 0
    for retry_round, retry_workers, wait_seconds in [(1, min(2, threads), 45), (2, 1, 90)]:
        if cancel_event is not None and cancel_event.is_set():
            break
        temp_errors = _temporary_errors_from_state(state_dir)
        retry_items: list[tuple[int, Path]] = []
        for m in temp_errors:
            pdf = _pdf_from_meta(m, input_dir)
            if pdf:
                retry_items.append((int(m.get("retry_idx") or len(retry_items) + 1), pdf))
        if not retry_items:
            break
        retry_rounds_done += 1
        _emit(
            progress_cb,
            stage="retry_wait",
            message=f"Errores temporales detectados: {len(retry_items)}. Reintento automático {retry_round}/2 en {wait_seconds}s con {retry_workers} hilo(s).",
            percent=min(99, int((completed / len(pdf_files)) * 100) if pdf_files else 0),
            total=len(pdf_files),
            current=completed,
        )
        # Espera cancelable y pausible
        slept = 0
        while slept < wait_seconds:
            if cancel_event is not None and cancel_event.is_set():
                break
            if pause_event is not None and pause_event.is_set():
                _wait_if_paused_or_cancelled(pause_event, cancel_event, progress_cb, "", "")
            time.sleep(1)
            slept += 1
        if cancel_event is not None and cancel_event.is_set():
            break
        _emit(progress_cb, stage="retry_start", message=f"Reprocesando {len(retry_items)} errores temporales en modo seguro.", percent=min(99, int((completed / len(pdf_files)) * 100) if pdf_files else 0))
        _run_batch(retry_items, retry_workers, retry_progress)

    retry_queue = _write_retry_outputs(out_dir, state_dir)

    summary = _collect_outputs_fast(pdf_files, input_dir, cache_index_path, out_dir, ai_config) if resume_fast else _collect_outputs(pdf_files, input_dir, raw_dir, norm_dir, state_dir, out_dir, ai_config)
    summary.threads_used = threads
    summary.output_dir = str(out_dir)
    summary.skipped_success = skipped_success
    summary.total_cost_estimated_usd = round(summary.total_cost_estimated_usd, 6)
    secs = []
    for row in [get_entry(cache_index_path, _quick_file_info(p, input_dir)["ruta_relativa"]) for p in pdf_files]:
        try:
            if row and row.get("meta_json") and Path(row["meta_json"]).exists():
                meta = _read_json(Path(row["meta_json"]))
                if meta.get("status") == "success" and meta.get("seconds"):
                    secs.append(float(meta["seconds"]))
        except Exception:
            pass
    summary.avg_seconds_per_pdf = round(sum(secs) / len(secs), 2) if secs else 0.0

    manifest = {
        "updated_at": datetime.now().isoformat(timespec="seconds"), "version": APP_VERSION,
        "total": summary.total, "success": summary.success, "errors": summary.errors,
        "archivos_ok_o_alerta": summary.ok, "archivos_revisar": summary.revisar,
        "skipped_success": summary.skipped_success, "threads_used": summary.threads_used,
        "provider": ai_config.provider, "model": ai_config.model, "mode": "pdf_directo_ia",
        "resume_fast": resume_fast, "cache_index": str(cache_index_path),
        "nota": "json_ai_raw es respuesta estructurada de IA; no es JSON OCR tipo Azure.",
        "total_prompt_tokens": summary.total_prompt_tokens, "total_output_tokens": summary.total_output_tokens,
        "total_tokens": summary.total_tokens, "total_cost_estimated_usd": summary.total_cost_estimated_usd,
        "avg_seconds_per_pdf": summary.avg_seconds_per_pdf,
        "retry_rounds_done": retry_rounds_done,
        "errores_reprocesables": len(retry_queue),
        "retry_queue": str(out_dir / "retry_queue.json"),
        "errores_reprocesables_csv": str(out_dir / "errores_reprocesables.csv"),
    }
    _safe_write_json(out_dir / "manifest.json", manifest)
    log.info("Finalizado. Total=%d OK=%d Errores=%d Revisar=%d Tokens=%d CostoUSD=%s", summary.total, summary.success, summary.errors, summary.revisar, summary.total_tokens, summary.total_cost_estimated_usd)
    log.removeHandler(fh); fh.close()
    _emit(progress_cb, stage="finished", message=f"Finalizado. OK={summary.success}, Errores={summary.errors}, Revisar={summary.revisar}, Costo USD={summary.total_cost_estimated_usd}. Salida: {summary.output_dir}", percent=100)
    return summary


def reprocess_temporary_errors(output_dir: str, folder_path: str, ai_config: AIConfig, ocr_config: OCRConfig, progress_cb: ProgressCallback = None, threads: int = 1) -> ProcessingSummary:
    """Reprocesa solo los errores temporales registrados en retry_queue.json/estado_pdf.

    Útil cuando se cayó internet o Gemini devolvió 503/429 durante un lote.
    No toca archivos ya exitosos.
    """
    out_dir = Path(output_dir)
    input_dir = Path(folder_path)
    if not out_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de resultados: {out_dir}")
    if not input_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de PDFs: {input_dir}")

    raw_dir = out_dir / "cache_ai" / "json_ai_raw"
    norm_dir = out_dir / "cache_ai" / "json_ai_normalizado"
    state_dir = out_dir / "estado_pdf"
    cache_index_path = out_dir / "cache_ai" / "cache_index.sqlite"
    init_index(cache_index_path)
    for d in [raw_dir, norm_dir, state_dir, cache_index_path.parent]:
        d.mkdir(parents=True, exist_ok=True)

    log_jsonl = out_dir / "process.jsonl"
    provider_max = safe_max_threads(ai_config.provider)
    workers = max(1, min(int(threads), min(2, provider_max)))
    temp_errors = _temporary_errors_from_state(state_dir)
    items: list[tuple[int, Path]] = []
    for idx, meta in enumerate(temp_errors, start=1):
        pdf = _pdf_from_meta(meta, input_dir)
        if pdf:
            items.append((idx, pdf))

    _emit(progress_cb, stage="retry_manual_scan", message=f"Errores temporales encontrados para reproceso: {len(items)}", percent=0, total=len(items), current=0)

    completed = 0
    lock = threading.Lock()

    def wrap(payload: dict) -> None:
        nonlocal completed
        if payload.get("stage") in {"done_file", "error_file", "cancelled_file"}:
            with lock:
                completed += 1
                pct = int((completed / len(items)) * 100) if items else 100
            payload = {**payload, "percent": pct, "completed": completed}
        _emit(progress_cb, **payload)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_process_single_pdf, pdf_path, input_dir, idx, len(items), ai_config, raw_dir, norm_dir, state_dir, wrap, log_jsonl, None, None): pdf_path
            for idx, pdf_path in items
        }
        for future in as_completed(futures):
            result = future.result()
            meta_path = result.get("meta")
            if meta_path:
                try:
                    meta = _read_json(Path(meta_path))
                    cache_stem = meta.get("cache_stem")
                    pdf_path = futures[future]
                    raw_path = raw_dir / f"{cache_stem}.json" if cache_stem else None
                    norm_path = norm_dir / f"{cache_stem}.normalizado.json" if cache_stem else None
                    upsert_entry(cache_index_path, _index_entry_from_meta(meta, raw_path, norm_path, Path(meta_path), pdf_path, input_dir))
                except Exception as exc:
                    log.debug("No se pudo actualizar índice en reproceso para %s: %s", futures.get(future), exc)

    retry_queue = _write_retry_outputs(out_dir, state_dir)
    pdf_files = sorted(input_dir.rglob("*.pdf"))
    summary = _collect_outputs_fast(pdf_files, input_dir, cache_index_path, out_dir, ai_config)
    summary.threads_used = workers
    summary.output_dir = str(out_dir)
    manifest_path = out_dir / "manifest_reproceso_errores.json"
    _safe_write_json(manifest_path, {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "version": APP_VERSION,
        "modo": "reprocess_temporary_errors",
        "input_dir": str(input_dir),
        "output_dir": str(out_dir),
        "errores_temporales_iniciales": len(items),
        "errores_reprocesables_restantes": len(retry_queue),
        "threads_used": workers,
        "provider": ai_config.provider,
        "model": ai_config.model,
    })
    _emit(progress_cb, stage="finished", message=f"Reproceso de errores finalizado. Errores reprocesables restantes: {len(retry_queue)}", percent=100)
    return summary



def reprocess_ai_cache(cache_or_output_dir: str, output_dir: str | None = None) -> ProcessingSummary:
    """Reprocesa json_ai_raw ya guardados sin llamar a la IA. Útil para cambiar reglas SAIRC sin volver a pagar API."""
    base = Path(cache_or_output_dir)
    raw_dir = base
    if (base / "cache_ai" / "json_ai_raw").exists():
        raw_dir = base / "cache_ai" / "json_ai_raw"
    out_dir = Path(output_dir) if output_dir else (base if (base / "cache_ai").exists() else base / "reproceso_sairc_v8_8")
    norm_dir = out_dir / "cache_ai" / "json_ai_normalizado"
    state_dir = out_dir / "estado_pdf"
    for d in [out_dir, norm_dir, state_dir]:
        d.mkdir(parents=True, exist_ok=True)
    raw_files = sorted(raw_dir.glob("*.json"))
    fake_pdf_files: list[Path] = []
    for raw_path in raw_files:
        raw = _read_json(raw_path)
        source = raw.get("_source") or {}
        rel = source.get("ruta_relativa") or raw_path.name.replace(".json", ".pdf")
        carpeta = source.get("carpeta_origen") or str(Path(rel).parent).replace(".", "")
        norm = normalize_ai_output(raw, ruta_relativa=rel, carpeta_origen=carpeta)
        norm_path = norm_dir / f"{raw_path.stem}.normalizado.json"
        _safe_write_json(norm_path, norm)
        meta = {
            "filename": Path(rel).name, "ruta_relativa": rel, "carpeta_origen": carpeta, "cache_stem": raw_path.stem,
            "status": "success", "mode": "reproceso_ai", "provider": (raw.get("_meta") or {}).get("provider"),
            "model": (raw.get("_meta") or {}).get("model"), "pages": None, "file_size_mb": None,
            "seconds": 0, "rows": len(raw.get("resultados") or []), "updated_at": datetime.now().isoformat(timespec="seconds"),
            "error_type": None, "error": None,
        }
        _safe_write_json(state_dir / f"{raw_path.stem}.meta.json", meta)
        # Path ficticio solo para colectar usando stem. Creamos lista y usamos modo de colector manual abajo.
        fake_pdf_files.append(Path(rel))
    # Colector específico para raw cache: no depende de hash de PDF.
    summary = ProcessingSummary(total=len(raw_files))
    archivo_rows=[]; control_rows=[]; normalizados=[]; sairc_rows=[]; pendientes=[]; raw_rows=[]; costos_rows=[]; error_rows=[]
    dummy_config = AIConfig(provider="gemini", model="reproceso_ai", api_key="")
    for raw_path in raw_files:
        raw = _read_json(raw_path)
        norm_path = norm_dir / f"{raw_path.stem}.normalizado.json"
        meta_path = state_dir / f"{raw_path.stem}.meta.json"
        norm = _read_json(norm_path); meta = _read_json(meta_path)
        archivo_rows.append(_row_archivo_from_meta(meta, raw, norm))
        cab = norm.get("cabecera") or {}
        control_rows.append(cab); sairc_rows.append(norm.get("sairc") or {})
        if str(cab.get("estado_archivo") or "").upper() in {"OK", "OK_CON_REGLA", "OK_CARGABLE", "OK_CON_ALERTA_CLINICA"}: summary.ok += 1
        else: summary.revisar += 1
        summary.success += 1
        usage = _token_usage(raw or {})
        summary.total_cost_estimated_usd += float(usage.get("cost_estimated_usd") or 0.0)
        summary.total_tokens += int(usage.get("total_token_count") or 0)
        for r in norm.get("resultados_normalizados") or []:
            normalizados.append({**{k: cab.get(k) for k in ["ruta_relativa", "paciente", "documento_archivo_pdf", "documento_identidad", "coincidencia_documento", "estado_identidad", "puede_cargarse_sairc", "laboratorio"]}, **r})
        pendientes.extend(norm.get("pendientes") or [])
        raw_rows.append({"ruta_relativa": cab.get("ruta_relativa"), "json_ai_raw": raw_path.name, "json_ai_normalizado": norm_path.name, "resultados_raw": len(raw.get("resultados") or [])})
        costos_rows.append({"ruta_relativa": cab.get("ruta_relativa"), "total_token_count": usage.get("total_token_count"), "costo_estimado_usd": usage.get("cost_estimated_usd")})
    resumen_rows=[{"version": APP_VERSION, "modo":"reproceso_ai", "total_json_ai_raw": len(raw_files), "procesados_ok": summary.success, "archivos_revisar": summary.revisar, "pendientes_revision": len(pendientes)}]
    _write_excel(out_dir, resumen_rows, control_rows, normalizados, sairc_rows, archivo_rows, pendientes, raw_rows, costos_rows, error_rows)
    _write_csv(out_dir / "resultados_normalizados.csv", normalizados)
    _write_sairc_csvs(out_dir, sairc_rows)
    _write_csv(out_dir / "pendientes_revision.csv", pendientes)
    summary.output_dir = str(out_dir)
    return summary
