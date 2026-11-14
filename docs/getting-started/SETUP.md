# Instalación y catálogo local

Los requisitos y comandos de instalación/apertura canónicos están en el
[README](../../README.md). Ejecute los comandos desde la raíz del proyecto.
El entorno validado es Windows x64, Python 3.13.14 y Tk 8.6.

## Preparar el catálogo

Un checkout no incluye descargas ni SQLite. Obtenga por separado un ZIP GTFS
estático de una fuente autorizada; los endpoints documentados en la investigación
no garantizan disponibilidad actual. Esta guía no ejecuta descargas.

Con un ZIP ya guardado localmente, el comando existente es:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker.catalog import data/probes/official_static.zip --source-url https://gtfs.transmilenio.gov.co/GTFS.zip
.\.venv\Scripts\python.exe -m transmitracker.catalog search 'Portal Norte'
```

La URL registra procedencia; el importador lee el ZIP local. El destino por
defecto es `data/catalog/official_20261112.sqlite3`. Para otra versión, seleccione
otra ruta con `--db` antes del subcomando; no sobrescriba el catálogo anterior.
Configure explícitamente el catálogo en la GUI. Los perfiles antiguos conservan
su hash; cambiar el catálogo no remapea IDs ni migra perfiles silenciosamente.

La fecha del nombre del archivo no acredita vigencia del calendario. Las
consultas de horarios requieren una fecha cubierta por los servicios publicados.
Para pruebas sin estos datos, use el diagnóstico sintético del README.

## Uso y ejemplos

La [guía de usuario](USAGE.md) explica ambos perfiles y sus estados.
`scripts/demo_phase2_1.py` prepara una demo técnica separada con el catálogo real
preexistente; `python -m transmitracker.gui --qa-demo` la abre. No es un perfil
personal ni tracking real. La demo anterior conserva `--demo`.

Perfiles: `data/gui/profiles.sqlite3`; preferencias: `data/gui/settings.json`.
Secretos opcionales: `.env`, texto sin cifrar. No se necesita una clave Croma
para usar el catálogo ni la GUI. Configurar claves o avisos no activa integraciones.
