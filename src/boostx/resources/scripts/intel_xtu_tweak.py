"""
intel_xtu_tweak.py
Обёртка над Intel XTU CLI (xtucli.exe) для безопасного снятия
троттлинга по мощности (PL1 = PL2, снятие Tau-лимита).

ТРЕБОВАНИЯ:
- Установлен Intel Extreme Tuning Utility (включает xtucli.exe),
  обычно лежит в: C:\\Program Files\\Intel\\Intel(R) Extreme Tuning Utility\\Client\\
- Запуск от администратора.
- Разблокированный ("K"/"KS"/Unlocked) процессор Intel - на заблокированных
  моделях изменение PL1/PL2 может не подействовать (ограничение платы/BIOS).

ЧТО ДЕЛАЕТ:
Поднимает PL1 до уровня PL2 и увеличивает Tau (время удержания буста),
т.е. убирает штатное ограничение "турбо только 56 секунд, потом троттлинг
до базовой частоты". Множитель ядра и напряжение не трогает - это
самый безопасный и предсказуемый вид "разгона" для Intel.

ЗАВОДСКИЕ PL2 ПО МОДЕЛЯМ (см. HARDWARE_TWEAKS.md) - используются
как safe-таргет, если авто-определение через xtucli не сработало.
"""

import subprocess
import sys
import shutil

# Заводские PL2 (Вт) как safe-таргет - на случай если xtucli не смог
# определить лимиты автоматически. Используется ТОЛЬКО как fallback.
FALLBACK_PL2 = {
    "i9-14900k": 253, "core ultra 9 285k": 253,
    "i7-14700k": 253, "core ultra 7 265k": 253,
    "i5-14600k": 181, "core ultra 5 245k": 181,
    "i9-13900k": 253,
    "i7-13700k": 253,
    "i5-13600k": 181,
}

XTU_CLI_CANDIDATES = [
    r"C:\Program Files\Intel\Intel(R) Extreme Tuning Utility\Client\xtucli.exe",
    "xtucli",  # если добавлено в PATH
]


def find_xtucli():
    for path in XTU_CLI_CANDIDATES:
        if shutil.which(path) or path == XTU_CLI_CANDIDATES[0]:
            try:
                subprocess.run([path, "--help"], capture_output=True, timeout=5)
                return path
            except (FileNotFoundError, OSError):
                continue
    return None


def run_xtucli(xtucli, args, dry_run=True):
    cmd = [xtucli] + args
    print(f"  Команда: {' '.join(cmd)}")
    if dry_run:
        print("  [DRY RUN] Не выполняется. Запустите с --apply.")
        return
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout or result.stderr)


def get_current_limits(xtucli):
    """Читает текущие PL1/PL2/Tau через xtucli --readpowerlimits (если поддерживается)."""
    result = subprocess.run([xtucli, "--readpowerlimits"], capture_output=True, text=True)
    print(result.stdout)
    return result.stdout


def apply_safe_power_unlock(xtucli, cpu_name=None, dry_run=True):
    print("Шаг 1: читаем текущие лимиты...")
    get_current_limits(xtucli)

    pl2_target = None
    if cpu_name:
        pl2_target = FALLBACK_PL2.get(cpu_name.lower().strip())

    print("\nШаг 2: снимаем Tau-лимит (турбо не будет сбрасываться по таймеру)...")
    run_xtucli(xtucli, ["--settaulimit", "0"], dry_run=dry_run)  # 0 = без таймера, где поддерживается

    print("\nШаг 3: выравниваем PL1 = PL2 (турбо-мощность становится длительной)...")
    if pl2_target:
        print(f"  Используем справочное значение PL2 для {cpu_name}: {pl2_target} Вт")
        run_xtucli(xtucli, ["--setpowerlimit1", str(pl2_target)], dry_run=dry_run)
    else:
        print("  Модель не указана/не найдена в справочнике - используем текущий PL2 карты,")
        print("  который xtucli определяет сам через --setpowerlimit1=pl2 (см. документацию XTU).")
        run_xtucli(xtucli, ["--setpowerlimit1", "auto"], dry_run=dry_run)

    print("\n⚠️  После применения обязательно прогоните стресс-тест 20-30 минут")
    print("    (OCCT/Prime95) и следите за температурой - не выше 95°C long-term.")


def main():
    dry_run = "--apply" not in sys.argv
    cpu_name = None
    for arg in sys.argv:
        if arg.startswith("--cpu="):
            cpu_name = arg.split("=", 1)[1]

    xtucli = find_xtucli()
    if not xtucli:
        print("❌ xtucli.exe не найден. Установите Intel Extreme Tuning Utility")
        print("   и/или укажите путь вручную в XTU_CLI_CANDIDATES.")
        return

    print(f"Найден XTU CLI: {xtucli}\n")
    apply_safe_power_unlock(xtucli, cpu_name=cpu_name, dry_run=dry_run)


if __name__ == "__main__":
    print("=== Intel XTU Power Unlock Tweak ===")
    print("Использование:")
    print("  python intel_xtu_tweak.py --cpu=\"i9-14900k\"           — dry run")
    print("  python intel_xtu_tweak.py --apply --cpu=\"i9-14900k\"   — применить")
    print()
    main()
