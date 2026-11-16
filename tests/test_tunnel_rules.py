from boostx.core.services.tunnel.rules import build_rule, is_specific_folder


def test_game_is_selected_by_its_install_folder_and_known_executables():
    rule = build_rule(
        "counter_strike_2",
        r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe",
        install_dir=r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive",
        extra_exes=("cs2.exe",),
    )
    assert rule.name == "counter_strike_2"
    assert rule.exes == ("cs2.exe",)  # not listed twice
    assert rule.dirs == (r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive",)


def test_launcher_elsewhere_still_selects_the_real_game_executable():
    rule = build_rule(
        "league_of_legends",
        r"C:\Riot Games\Riot Client\RiotClientServices.exe",
        extra_exes=("League of Legends.exe",),
    )
    assert rule.exes == ("RiotClientServices.exe", "League of Legends.exe")
    assert rule.dirs == (r"C:\Riot Games\Riot Client",)


def test_executable_in_a_shared_folder_does_not_select_the_whole_folder():
    for path in (
        r"C:\game.exe",
        r"C:\Games\game.exe",
        r"C:\Users\me\Desktop\game.exe",
        r"C:\Users\me\Downloads\game.exe",
        r"C:\Program Files\game.exe",
        r"C:\Windows\System32\game.exe",
        r"D:\SteamLibrary\steamapps\common\game.exe",
    ):
        rule = build_rule("x", path)
        assert rule.dirs == (), path
        assert rule.exes == ("game.exe",)


def test_shared_install_dir_falls_back_to_the_executables_own_folder():
    rule = build_rule("x", r"D:\Games\Title\bin\game.exe", install_dir=r"D:\Games")
    assert rule.dirs == (r"D:\Games\Title\bin",)


def test_non_windows_paths_never_produce_a_folder_rule():
    rule = build_rule("discord", "/Applications/Discord.app", install_dir="/Applications")
    assert rule.dirs == ()
    assert rule.exes == ()


def test_specific_folder_needs_a_drive_and_depth():
    assert is_specific_folder(r"C:\Games\Title")
    assert is_specific_folder(r"C:\Users\me\AppData\Local\Discord")
    assert not is_specific_folder(r"C:\Title")
    assert not is_specific_folder(r"Games\Title\bin")
    assert not is_specific_folder(r"C:\Users\me\AppData\Local")
