import sys
import subprocess
from codecarbon import EmissionsTracker


def main():
    # Validamos que nos pasen un script para auditar
    if len(sys.argv) < 2:
        print("❌ Error: Debes indicar qué script auditar.")
        print("Uso: python emissions_runner.py <tu_script.py>")
        sys.exit(1)

    target_script = sys.argv[1]

    # Configuramos el tracker.
    # 'project_name' usa el nombre del script para diferenciar reportes si auditas varios.
    tracker = EmissionsTracker(
        project_name=f"Audit_{target_script}",
        output_dir=".",
        measure_power_secs=1
    )

    print(f"\n[ECO-RUNNER] 🛡️ Iniciando envoltura verde sobre: {target_script}")
    tracker.start()

    try:
        # Ejecutamos el script del proyecto como un proceso hijo
        # Esto mantiene tu proyecto aislado del código de medición
        result = subprocess.run(["python", target_script], check=False)

        if result.returncode != 0:
            print(
                f"\n⚠️ Alerta: {target_script} falló con código {result.returncode}, pero mediremos el consumo igual.")

    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo '{target_script}'")
    except Exception as e:
        print(f"❌ Error inesperado ejecutando el script: {e}")
    finally:
        # Detenemos la medición pase lo que pase
        emissions = tracker.stop()
        print(f"[ECO-RUNNER] 🌳 Auditoría finalizada. Reporte generado en emissions.csv")
        print(f"[ECO-RUNNER] Total CO2 estimado: {emissions} kg\n")


if __name__ == "__main__":
    main()