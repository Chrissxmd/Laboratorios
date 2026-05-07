from __future__ import annotations

import argparse
import getpass
import logging
from datetime import datetime

from core.ai import AIConfig
from core.pdf_utils import OCRConfig
from core.processor import process_folder, reprocess_ai_cache, reprocess_temporary_errors, safe_max_threads

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Lab Extractor Gemini/IA SAIRC v8.9 — PDF directo a IA + Excel final SAIRC + cache rápido.\n"
            "Nota: json_ai_raw es cache de respuesta IA; no es JSON OCR tipo Azure."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--modo", choices=["pdf", "reprocesar_ai", "reprocesar_errores"], default="pdf",
                        help="pdf: envía PDF a IA. reprocesar_ai: genera Excel desde cache json_ai_raw. reprocesar_errores: reintenta solo errores temporales.")
    parser.add_argument("--input", required=True, help="Carpeta con PDFs, carpeta/cache json_ai_raw, o carpeta de PDFs si --modo reprocesar_errores")
    parser.add_argument("--output-dir", default="", help="Carpeta de salida. En reprocesar_errores debe ser la carpeta de resultados con retry_queue.json.")
    parser.add_argument("--provider", choices=["claude", "openai", "gemini", "deepseek"], default="gemini")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Modelo IA")
    parser.add_argument("--api-key", default="", help="API key. Si se omite en modo pdf, se pedirá por consola.")
    parser.add_argument("--threads", type=int, default=4, help="Hilos paralelos. Producción recomendada: 4; rápido: 6. Se recorta al límite seguro del proveedor.")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=180, help="Timeout en segundos por llamada a la API.")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--rpm", type=int, default=180, help="Máximo de solicitudes por minuto a la API. Producción recomendada: 180.")
    parser.add_argument("--cooldown-429", type=int, default=45, help="Pausa base global al detectar HTTP 429.")
    parser.add_argument("--count-tokens", action="store_true", help="Activa countTokens previo. Desactivado por defecto para reducir latencia.")
    parser.add_argument("--no-count-tokens", action="store_true", help="Compatibilidad: countTokens ya está desactivado por defecto.")
    parser.add_argument("--resume-fast", action="store_true", default=True, help="Reanuda usando cache_index.sqlite sin validar todo el cache al inicio.")
    parser.add_argument("--no-resume-fast", dest="resume_fast", action="store_false", help="Desactiva reanudación rápida y usa validación clásica.")
    parser.add_argument("--rebuild-index", action="store_true", help="Reconstruye cache_index.sqlite desde estado_pdf antes de iniciar.")
    parser.add_argument("--skip-cache-validation", action="store_true", help="No valida existencia de archivos raw/norm/meta al usar índice. Más rápido, usar solo si no moviste cache.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.modo == "reprocesar_ai":
        print("=== Lab Extractor Gemini/IA SAIRC v8.9 — Reprocesar cache IA ===")
        print(f"Entrada: {args.input}")
        try:
            result = reprocess_ai_cache(args.input, output_dir=args.output_dir or None)
        except Exception as exc:
            print(f"\n[ERROR] {exc}")
            return 1
        print("\n=== RESUMEN ===")
        print(f"JSON IA raw       : {result.total}")
        print(f"Procesados OK     : {result.success}")
        print(f"Archivos revisar  : {result.revisar}")
        print(f"Salida            : {result.output_dir}")
        return 0

    if args.modo == "reprocesar_errores":
        if not args.output_dir:
            print("[ERROR] Para --modo reprocesar_errores debes indicar --output-dir con la carpeta de resultados.")
            return 2
        api_key = args.api_key.strip() or getpass.getpass("API key: ").strip()
        if not api_key:
            print("[ERROR] No se recibió API key.")
            return 2
        config = AIConfig(
            provider=args.provider,
            model=args.model.strip(),
            api_key=api_key,
            temperature=args.temperature,
            timeout_seconds=args.timeout,
            max_retries=args.retries,
            requests_per_minute=args.rpm,
            cooldown_on_429_seconds=args.cooldown_429,
            enable_token_count=bool(args.count_tokens and not args.no_count_tokens),
        )
        def on_progress(payload: dict):
            now = datetime.now().strftime("%H:%M:%S")
            print(f"[{now}] [{payload.get('percent', 0):>3}%] {payload.get('message', '')}", flush=True)
        try:
            result = reprocess_temporary_errors(args.output_dir, args.input, config, OCRConfig(), progress_cb=on_progress, threads=min(2, args.threads))
        except Exception as exc:
            print(f"\n[ERROR] {exc}")
            return 1
        print("\n=== RESUMEN REPROCESO ERRORES ===")
        print(f"Total PDF         : {result.total}")
        print(f"OK                : {result.success}")
        print(f"Errores           : {result.errors}")
        print(f"Salida            : {result.output_dir}")
        return 0

    api_key = args.api_key.strip() or getpass.getpass("API key: ").strip()
    if not api_key:
        print("[ERROR] No se recibió API key.")
        return 2

    provider_max = safe_max_threads(args.provider)
    threads = max(1, min(args.threads, provider_max))
    if threads != args.threads:
        print(f"[INFO] Hilos recortados de {args.threads} a {threads} (límite seguro para {args.provider})")

    config = AIConfig(
        provider=args.provider,
        model=args.model.strip(),
        api_key=api_key,
        temperature=args.temperature,
        timeout_seconds=args.timeout,
        max_retries=args.retries,
        requests_per_minute=args.rpm,
        cooldown_on_429_seconds=args.cooldown_429,
        enable_token_count=bool(args.count_tokens and not args.no_count_tokens),
    )
    ocr_config = OCRConfig()  # compatibilidad; no usa OCR local

    def on_progress(payload: dict):
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] [{payload.get('percent', 0):>3}%] {payload.get('message', '')}", flush=True)

    print("=== Lab Extractor Gemini/IA SAIRC v8.9 — PDF directo + Excel SAIRC ===")
    print(f"Proveedor : {config.provider}")
    print(f"Modelo    : {config.model}")
    print(f"Hilos     : {threads} (máx. seguro: {provider_max})")
    print("Modo      : PDF directo a IA; cache json_ai_raw no es JSON OCR Azure")
    print(f"Cache fast: {args.resume_fast} | rebuild-index: {args.rebuild_index}")
    print(f"Carpeta   : {args.input}")
    if args.output_dir:
        print(f"Salida    : {args.output_dir}")
    print()

    try:
        result = process_folder(
            args.input, config, ocr_config, progress_cb=on_progress, threads=threads,
            output_dir=args.output_dir or None, resume_fast=args.resume_fast,
            rebuild_index=args.rebuild_index, skip_cache_validation=args.skip_cache_validation,
        )
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        return 1

    print("\n=== RESUMEN ===")
    print(f"Hilos usados      : {result.threads_used}")
    print(f"Total PDF         : {result.total}")
    print(f"OK                : {result.success}")
    print(f"Errores           : {result.errors}")
    print(f"Archivos revisar  : {result.revisar}")
    print(f"Reutilizados      : {result.skipped_success}")
    print(f"Tokens totales    : {result.total_tokens}")
    print(f"Costo estimado USD: {result.total_cost_estimated_usd}")
    print(f"Salida            : {result.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
