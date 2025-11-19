import sys
import os
import subprocess
import datetime
from codecarbon import EmissionsTracker
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS


def send_to_influx(data, project_name):
    """
    Envía las métricas a InfluxDB si las credenciales existen.
    """
    url = os.getenv("INFLUXDB_URL")
    token = os.getenv("INFLUXDB_TOKEN")
    org = os.getenv("INFLUXDB_ORG")
    bucket = os.getenv("INFLUXDB_BUCKET")

    # Datos de contexto Git (inyectados por GitHub Actions)
    commit_sha = os.getenv("GITHUB_SHA", "local-run")
    branch_name = os.getenv("GITHUB_REF_NAME", "unknown")

    if not all([url, token, org, bucket]):
        print("⚠️ InfluxDB no configurado. Saltando envío de datos históricos.")
        return

    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        write_api = client.write_api(write_options=SYNCHRONOUS)

        # Creamos el punto de dato (Métrica profesional)
        point = (
            Point("carbon_footprint")
            .tag("project", project_name)
            .tag("branch", branch_name)
            .tag("commit", commit_sha[:7])
            .field("emissions_kg", float(data.emissions))
            .field("energy_kwh", float(data.cpu_energy))
            .field("duration_sec", float(data.duration))
            .time(datetime.datetime.utcnow())
        )

        write_api.write(bucket=bucket, org=org, record=point)
        print(f"✅ Datos históricos guardados en InfluxDB ({url})")

    except Exception as e:
        print(f"❌ Error conectando a InfluxDB: {e}")


def main():
    if len(sys.argv) < 2:
        print("❌ Error: Uso: python emissions_runner_influx.py <script.py>")
        sys.exit(1)

    target_script = sys.argv[1]
    project_name = os.getenv("GITHUB_REPOSITORY", "local-project").split("/")[-1]

    # Configuración CodeCarbon
    tracker = EmissionsTracker(
        project_name=project_name,
        output_dir=".",
        measure_power_secs=1,
        save_to_file=True  # Seguimos guardando CSV por seguridad
    )

    print(f"\n[ECO-RUNNER] 🛡️ Iniciando auditoría sobre: {target_script}")
    tracker.start()

    try:
        subprocess.run(["python", target_script], check=False)
    finally:
        emissions = tracker.stop()
        print(f"[ECO-RUNNER] CO2: {emissions} kg")

        # PASO NUEVO: Enviar a base de datos histórica
        send_to_influx(tracker.final_emissions_data, project_name)


if __name__ == "__main__":
    main()