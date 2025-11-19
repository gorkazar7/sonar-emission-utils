import sys
import os
import subprocess
import datetime
import argparse
import time
from codecarbon import EmissionsTracker
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Factor promedio de Eficacia del Uso del Agua (Water Usage Effectiveness - WUE)
# Si CodeCarbon no detecta el dato exacto, usamos el promedio de la industria (L/kWh)
WUE_AVG_L_PER_KWH = 0.71


def send_to_influx(data, project_name, tags=None):
    """
    Envía las métricas a InfluxDB con soporte para tags personalizados.
    """
    url = os.getenv("INFLUXDB_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
    token = os.getenv("INFLUXDB_TOKEN",
                      "mzDnVmtj8dLOuE1Oo9CWaYWwBCJ0p6MU9ilTtlArl0heBCOk1_wqPEQk17OBZfksv44esWLmZYer-LBv7j8CRQ==")
    org = os.getenv("INFLUXDB_ORG", "Dev Team")
    bucket = os.getenv("INFLUXDB_BUCKET", "greenit")

    commit_sha = os.getenv("GITHUB_SHA", "local-run")
    branch_name = os.getenv("GITHUB_REF_NAME", "unknown")

    if not all([url, token, org, bucket]):
        print("⚠️ InfluxDB no configurado. Saltando envío.")
        return

    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        write_api = client.write_api(write_options=SYNCHRONOUS)

        # --- LÓGICA DE AGUA ---
        # Intentamos obtener el dato nativo, si no, estimamos con WUE
        water_val = getattr(data, 'water_consumed', None)
        if water_val is None or float(water_val) == 0.0:
            # Calculamos usando el total de energía consumida * factor WUE
            # Usamos energy_consumed (Total) si existe, si no, cpu_energy
            total_energy = getattr(data, 'energy_consumed', data.cpu_energy)
            water_val = float(total_energy) * WUE_AVG_L_PER_KWH

        point = (
            Point("carbon_footprint")
            .tag("project", project_name)
            .tag("branch", branch_name)
            .tag("commit", commit_sha[:7])
            .field("emissions_kg", float(data.emissions))
            .field("energy_kwh", float(data.cpu_energy))
            .field("water_liters", float(water_val))
            .field("duration_sec", float(data.duration))
            .time(datetime.datetime.utcnow())
        )

        # Añadimos tags extra si existen (ej: endpoint=login, type=api_test)
        if tags:
            for key, value in tags.items():
                point.tag(key, value)

        write_api.write(bucket=bucket, org=org, record=point)
        print(f"✅ Datos históricos (incl. Agua) guardados en InfluxDB")

    except Exception as e:
        print(f"❌ Error conectando a InfluxDB: {e}")


def main():
    # --- MEJORA 1: Argument Parser Robusto ---
    parser = argparse.ArgumentParser(description="Auditor de Carbono para CI/CD")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="El comando a ejecutar y medir (ej: python script.py o pytest)")
    parser.add_argument("--tag", action="append", help="Tags extra para InfluxDB en formato clave=valor")

    args = parser.parse_args()

    if not args.command:
        print("❌ Error: Debes indicar un comando.")
        print("Uso: python emissions_runner.py -- python main.py")
        print("Uso: python emissions_runner.py -- pytest tests/")
        sys.exit(1)

    target_command = args.command
    project_name = os.getenv("GITHUB_REPOSITORY", os.path.basename(os.getcwd())).split("/")[-1]

    custom_tags = {}
    if args.tag:
        for tag in args.tag:
            try:
                k, v = tag.split("=")
                custom_tags[k] = v
            except ValueError:
                pass

    tracker = EmissionsTracker(
        project_name=project_name,
        output_dir=".",
        measure_power_secs=0.5,
        save_to_file=True
    )

    print(f"\n[ECO-RUNNER] 🛡️ Comando a auditar: {' '.join(target_command)}")
    tracker.start()

    start_time = time.time()
    try:
        # --- MEJORA 2: Ejecución Agnóstica ---
        result = subprocess.run(target_command, check=False)

        if result.returncode != 0:
            print(f"\n⚠️ El comando falló con código {result.returncode}")
            custom_tags["status"] = "failed"
        else:
            custom_tags["status"] = "success"

    except FileNotFoundError:
        print(f"❌ Error: No se encontró el ejecutable para: {target_command[0]}")
    except Exception as e:
        print(f"❌ Error crítico: {e}")
    finally:
        emissions = tracker.stop()
        duration = time.time() - start_time

        # Recuperamos el objeto de datos final
        data = tracker.final_emissions_data

        # Calculamos agua para mostrar en consola
        water_consumed = getattr(data, 'water_consumed', None)
        is_estimated = False

        if water_consumed is None or float(water_consumed) == 0.0:
            total_energy = getattr(data, 'energy_consumed', data.cpu_energy)
            water_consumed = float(total_energy) * WUE_AVG_L_PER_KWH
            is_estimated = True

        print(f"[ECO-RUNNER] Reporte Final:")
        print(f"   ⏱️  Duración: {duration:.2f}s")
        print(f"   💨 CO2:      {emissions} kg")
        print(f"   ⚡ Energía:  {data.cpu_energy} kWh")
        print(f"   💧 Agua:     {float(water_consumed):.6f} L {'(Estimado WUE)' if is_estimated else '(Nativo)'}")

        send_to_influx(data, project_name, custom_tags)


if __name__ == "__main__":
    main()