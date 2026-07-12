"""
amd_pbo_tweak.py
Обёртка над ryzenadj (open-source CLI) для применения PBO Advanced
с безопасными лимитами PPT/TDC/EDC по модели процессора.

ПОЧЕМУ ryzenadj, а не Ryzen Master:
Ryzen Master не имеет официального CLI/SDK. ryzenadj - открытый,
широко используемый инструмент (тот же принцип доступа к SMU,
что использует сам Ryzen Master).
https://github.com/FlyGoat/RyzenAdj - скачайте отдельно, здесь только обёртка.

ТРЕБОВАНИЯ:
- ryzenadj.exe (Windows) в PATH или рядом со скриптом
- Запуск от администратора
- Отключён Secure Boot / включён Test Mode на некоторых системах
  (ryzenadj использует WinRing0-подобный доступ к SMU)

ФИЛОСОФИЯ (см. HARDWARE_TWEAKS.md):
AMD официально рекомендует PBO в режиме Auto, а не жёсткие ручные offset.
Скрипт поднимает лимиты PPT/TDC/EDC до "Advanced"-уровня из таблицы,
но НЕ трогает Curve Optimizer (per-core voltage offset) - это самая
рискованная настройка и её нужно подбирать только вручную с тестами.
"""

import subprocess
import sys
import shutil

# Safe PBO limits (Вт / А) - см. обоснование в HARDWARE_TWEAKS.md
PBO_PROFILES = {
    "9950x3d": {"ppt": 200, "tdc": 160, "edc": 225},
    "9950x":   {"ppt": 200, "tdc": 160, "edc": 225},
    "9900x":   {"ppt": 150, "tdc": 120, "edc": 170},
    "9800x3d": {"ppt": 162, "tdc": 130, "edc": 225},
    "9700x":   {"ppt": 105, "tdc": 75,  "edc": 150},
    "9600x":   {"ppt": 105, "tdc": 75,  "edc": 150},
    "7950x3d": {"ppt": 162, "tdc": 130, "edc": 225},
    "7900x":   {"ppt": 200, "tdc": 160, "edc": 225},
    "7800x3d": {"ppt": 162, "tdc": 130, "edc": 225},
    "7600x":   {"ppt": 142, "tdc": 90,  "edc": 170},
}


def find_ryzenadj():
    path = shutil.which("ryzenadj") or shutil.which("ryzenadj.exe")
    if path:
        return path
    return "./ryzenadj.exe"  # если лежит рядом со скриптом


def read_current_state(ryzenadj):
    result = subprocess.run([ryzenadj, "-i"], capture_output=True, text=True)
    print(result.stdout or result.stderr)


def apply_pbo(ryzenadj, cpu_model, dry_run=True):
    profile = PBO_PROFILES.get(cpu_model.lower().strip())
    if not profile:
        print(f"❌ Модель '{cpu_model}' не найдена в справочнике.")
        print(f"   Доступные модели: {', '.join(PBO_PROFILES.keys())}")
        return

    print(f"Профиль для {cpu_model}: PPT={profile['ppt']}W, "
          f"TDC={profile['tdc']}A, EDC={profile['edc']}A")

    cmd = [
        ryzenadj,
        f"--stapm-limit={profile['ppt'] * 1000}",
        f"--fast-limit={profile['ppt'] * 1000}",
        f"--slow-limit={profile['ppt'] * 1000}",
        f"--tctl-temp=95",
        f"--vrm-current={profile['tdc'] * 1000}",
        f"--vrmmax-current={profile['edc'] * 1000}",
    ]

    print(f"  Команда: {' '.join(cmd)}")
    if dry_run:
        print("  [DRY RUN] Не выполняется. Запустите с --apply.")
        return

    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout or result.stderr)
    print("✅ Применено (лимиты сбрасываются при перезагрузке - при необходимости")
    print("   добавьте скрипт в автозагрузку).")
    print("\n⚠️  Прогоните стресс-тест (Cinebench R23 loop / OCCT) 20-30 минут")
    print("    и проверьте температуру (не выше 90-95°C для не-X3D, 85-90°C для X3D).")


def main():
    dry_run = "--apply" not in sys.argv
    cpu_model = None
    for arg in sys.argv:
        if arg.startswith("--cpu="):
            cpu_model = arg.split("=", 1)[1]

    ryzenadj = find_ryzenadj()

    if "--info" in sys.argv:
        read_current_state(ryzenadj)
        return

    if not cpu_model:
        print("❌ Укажите модель: --cpu=\"7800x3d\"")
        print(f"   Доступные: {', '.join(PBO_PROFILES.keys())}")
        return

    apply_pbo(ryzenadj, cpu_model, dry_run=dry_run)


if __name__ == "__main__":
    print("=== AMD PBO Safe Tweak (via ryzenadj) ===")
    print("Использование:")
    print("  python amd_pbo_tweak.py --info                    — текущее состояние")
    print("  python amd_pbo_tweak.py --cpu=\"7800x3d\"            — dry run")
    print("  python amd_pbo_tweak.py --apply --cpu=\"7800x3d\"    — применить")
    print()
    main()
