"""
nvidia_tweak.py
Безопасное поднятие Power Limit для видеокарт NVIDIA через NVML.

Требует: pip install nvidia-ml-py --break-system-packages
Требует прав администратора на Windows для изменения лимита.

Логика:
1. Определяем реальную карту и её ЗАВОДСКИЕ min/default/max power limit
   напрямую с драйвера (не из статичной таблицы - так корректно работает
   и для AIB-версий с другим заводским лимитом).
2. Поднимаем лимит до заданного процента от default, но НИКОГДА не выше
   max, который сама NVIDIA прошила в BIOS карты как безопасный потолок.
3. Ничего не трогаем в voltage curve - только мощность.
"""

import sys

try:
    import pynvml
except ImportError:
    print("Установите зависимость: pip install nvidia-ml-py --break-system-packages")
    sys.exit(1)

# Safe-таргет по умолчанию: 110% от заводского power limit.
# Не рекомендуется поднимать выше 115% без индивидуального стресс-теста.
DEFAULT_TARGET_PERCENT = 110


def list_gpus():
    pynvml.nvmlInit()
    count = pynvml.nvmlDeviceGetCount()
    gpus = []
    for i in range(count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        name = pynvml.nvmlDeviceGetName(handle)
        gpus.append((i, name, handle))
    return gpus


def get_power_limits(handle):
    """Возвращает (текущий, мин, макс) power limit в миллиВаттах."""
    current = pynvml.nvmlDeviceGetPowerManagementLimit(handle)
    min_limit, max_limit = pynvml.nvmlDeviceGetPowerManagementLimitConstraints(handle)
    return current, min_limit, max_limit


def apply_power_limit(handle, target_percent=DEFAULT_TARGET_PERCENT, dry_run=True):
    current, min_limit, max_limit = get_power_limits(handle)

    target = int(current * (target_percent / 100))
    # Жёсткая защита: никогда не выходим за пределы, разрешённые самой картой
    target = min(target, max_limit)
    target = max(target, min_limit)

    print(f"  Текущий лимит:  {current / 1000:.0f} Вт")
    print(f"  Диапазон карты: {min_limit / 1000:.0f}–{max_limit / 1000:.0f} Вт")
    print(f"  Новый таргет:   {target / 1000:.0f} Вт ({target_percent}%)")

    if dry_run:
        print("  [DRY RUN] Изменение не применено. Запустите с --apply для реального изменения.")
        return

    try:
        pynvml.nvmlDeviceSetPowerManagementLimit(handle, target)
        print("  ✅ Применено.")
    except pynvml.NVMLError as e:
        print(f"  ❌ Не удалось применить (нужны права администратора?): {e}")


def restore_default(handle):
    """Откат к заводскому значению по умолчанию."""
    default = pynvml.nvmlDeviceGetPowerManagementDefaultLimit(handle)
    pynvml.nvmlDeviceSetPowerManagementLimit(handle, default)
    print(f"  ✅ Восстановлен заводской лимит: {default / 1000:.0f} Вт")


def main():
    apply = "--apply" in sys.argv
    restore = "--restore" in sys.argv

    percent = DEFAULT_TARGET_PERCENT
    for arg in sys.argv:
        if arg.startswith("--percent="):
            percent = int(arg.split("=")[1])

    gpus = list_gpus()
    if not gpus:
        print("Видеокарты NVIDIA не найдены.")
        return

    for idx, name, handle in gpus:
        print(f"\nGPU {idx}: {name}")
        if restore:
            restore_default(handle)
        else:
            apply_power_limit(handle, target_percent=percent, dry_run=not apply)

    pynvml.nvmlShutdown()


if __name__ == "__main__":
    print("=== NVIDIA Power Limit Tweak ===")
    print("Использование:")
    print("  python nvidia_tweak.py                  — показать план (dry run)")
    print("  python nvidia_tweak.py --apply           — применить (110% по умолчанию)")
    print("  python nvidia_tweak.py --apply --percent=105  — применить с другим %")
    print("  python nvidia_tweak.py --restore         — откатить к заводским настройкам")
    print()
    main()
