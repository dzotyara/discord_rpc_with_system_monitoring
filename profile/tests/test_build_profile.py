import contextlib
import datetime as dt
import io
import json
import shutil
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "snapshot.json"  # frozen: data/snapshot.json changes daily
sys.path.insert(0, str(ROOT / "scripts"))

import build_profile as bp  # noqa: E402

NOW = dt.datetime(2026, 9, 27, 7, 30, tzinfo=dt.UTC)
SYSTEM = {
    "cpu_model": "AMD EPYC 7763",
    "cpu_count": 4,
    "cpu_percent": 12.5,
    "mem_total": 16 * 1024**3,
    "mem_used": 2 * 1024**3,
    "swap_total": 4 * 1024**3,
    "swap_used": 0,
}


def quiet(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
        return function(*args, **kwargs), err.getvalue()


API_RESPONSES = {
    "/users/dzotyara": {
        "login": "dzotyara",
        "name": "Nikita",
        "created_at": "2020-07-30T14:41:45Z",
        "public_repos": 3,
        "followers": 2,
    },
    "/users/dzotyara/repos?per_page=100&type=owner&sort=pushed": [
        {
            "name": "backseat",
            "fork": False,
            "stargazers_count": 5,
            "size": 900,
            "pushed_at": "2026-09-27T06:44:26Z",
            "description": "Bots",
        },
        {"name": "dzotyara", "fork": False, "stargazers_count": 1, "size": 10, "pushed_at": "2026-09-27T07:00:00Z"},
        {
            "name": "WarThunderDiscordRPC_Fork",
            "fork": True,
            "stargazers_count": 0,
            "size": 50,
            "pushed_at": "2025-12-20T08:08:56Z",
        },
    ],
    "/repos/dzotyara/backseat/languages": {"Python": 1000, "HTML": 100},
    "/graphql": {"data": {"user": {"contributionsCollection": {"contributionCalendar": {"totalContributions": 321}}}}},
}


class UptimeTest(unittest.TestCase):
    def test_borrows_days_from_the_previous_month(self):
        start = dt.datetime(2020, 7, 30, 14, 41, tzinfo=dt.UTC)
        self.assertEqual(bp.human_uptime(start, NOW), "6 лет, 1 месяц, 28 дней")

    def test_borrows_months_across_new_year(self):
        start = dt.datetime(2025, 11, 30, tzinfo=dt.UTC)
        now = dt.datetime(2026, 1, 15, tzinfo=dt.UTC)
        self.assertEqual(bp.human_uptime(start, now), "1 месяц, 16 дней")

    def test_singular_and_empty_parts(self):
        start = dt.datetime(2025, 9, 26, tzinfo=dt.UTC)
        self.assertEqual(bp.human_uptime(start, NOW), "1 год, 1 день")
        self.assertEqual(bp.human_uptime(NOW, NOW), "0 дней")


class NumbersTest(unittest.TestCase):
    def test_top_languages_fold_the_tail_into_other(self):
        languages = bp.top_languages({"Python": 900, "HTML": 50, "CSS": 30, "Shell": 15, "Go": 5})
        self.assertEqual([name for name, _, _ in languages], ["Python", "HTML", "CSS", "Другое"])
        self.assertAlmostEqual(sum(share for _, share, _ in languages), 100)
        self.assertEqual(languages[0][2], "#3572A5")
        self.assertEqual(bp.top_languages({}), [])

    def test_russian_plurals(self):
        forms = ("год", "года", "лет")
        cases = {
            1: "год",
            2: "года",
            4: "года",
            5: "лет",
            11: "лет",
            12: "лет",
            14: "лет",
            21: "год",
            22: "года",
            25: "лет",
            101: "год",
            111: "лет",
            0: "лет",
        }
        for n, expected in cases.items():
            self.assertEqual(bp.plural(n, *forms), expected, n)
        self.assertEqual(bp.count(2, "подписчик", "подписчика", "подписчиков"), "2 подписчика")

    def test_pct(self):
        self.assertEqual(bp.pct(0.4), "<1%")
        self.assertEqual(bp.pct(93.4), "93%")

    def test_pushed_when(self):
        self.assertEqual(bp.pushed_when(NOW - dt.timedelta(hours=1), NOW), "сегодня")
        self.assertEqual(bp.pushed_when(NOW - dt.timedelta(days=1), NOW), "вчера")
        self.assertEqual(bp.pushed_when(NOW - dt.timedelta(days=3), NOW), "3 дня назад")
        self.assertEqual(bp.pushed_when(dt.datetime(2026, 8, 15, tzinfo=dt.UTC), NOW), "15 авг")
        self.assertEqual(bp.pushed_when(dt.datetime(2025, 12, 20, tzinfo=dt.UTC), NOW), "20 дек 2025")

    def test_discrete_keeps_the_last_value_of_a_moment(self):
        key_times, values = bp.discrete([(0, 0), (0.5, 1), (0.50001, 2), (1.5, 3)], 2.0)
        self.assertEqual(key_times, "0;0.25;0.75")
        self.assertEqual(values, "0;2;3")

    def test_fit(self):
        self.assertEqual(bp.fit("short", 10), "short")
        self.assertEqual(bp.fit("a much longer line", 8), "a much…")


class ReposTest(unittest.TestCase):
    def test_own_repos_skip_forks_archives_empty_repos_and_the_profile_repo(self):
        repos = [
            {"name": "backseat"},
            {"name": "some-fork", "fork": True},
            {"name": "old", "archived": True},
            {"name": "empty", "size": 0},
            {"name": "DzOtYaRa"},
            {"name": "size-unknown", "size": None},
        ]
        self.assertEqual([repo["name"] for repo in bp.own_repos(repos, "dzotyara")], ["backseat", "size-unknown"])


class FetchTest(unittest.TestCase):
    def fake_get(self, calls, graphql=None):
        def get(url, token=None, payload=None):
            path = url.removeprefix(bp.API)
            calls.append((path, token, payload))
            if path == "/graphql" and graphql is not None:
                return graphql
            return API_RESPONSES[path]

        return get

    def test_snapshot_shape(self):
        calls = []
        snap = bp.fetch_github("dzotyara", "t0ken", get=self.fake_get(calls), now=NOW)
        self.assertEqual(snap["languages"], {"Python": 1000, "HTML": 100})  # no fork, no profile repo
        self.assertEqual(snap["contributions_last_year"], 321)
        self.assertEqual(snap["fetched_at"], "2026-09-27T07:30:00Z")
        self.assertEqual([repo["stars"] for repo in snap["repos"]], [5, 1, 0])
        self.assertEqual(snap["user"]["public_repos"], 3)
        self.assertTrue(all(token == "t0ken" for _, token, _ in calls))
        self.assertEqual(calls[-1][2]["variables"], {"login": "dzotyara"})

    def test_no_graphql_without_a_token(self):
        calls = []
        snap = bp.fetch_github("dzotyara", None, get=self.fake_get(calls), now=NOW)
        self.assertIsNone(snap["contributions_last_year"])
        self.assertNotIn("/graphql", [path for path, _, _ in calls])

    def test_graphql_errors_do_not_fail_the_fetch(self):
        get = self.fake_get([], graphql={"errors": [{"message": "nope"}], "data": None})
        snap, err = quiet(bp.fetch_github, "dzotyara", "t0ken", get=get, now=NOW)
        self.assertIsNone(snap["contributions_last_year"])
        self.assertIn("contributions unavailable", err)


class SystemStatsTest(unittest.TestCase):
    def test_reads_cpu_memory_and_swap_from_proc(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp)
            (proc / "cpuinfo").write_text("processor\t: 0\nmodel name\t: AMD EPYC 7763 64-Core Processor\n")
            (proc / "meminfo").write_text(
                "MemTotal: 16000000 kB\nMemFree: 1000000 kB\nMemAvailable: 12000000 kB\n"
                "SwapTotal: 4194304 kB\nSwapFree: 4194304 kB\n"
            )
            samples = iter(["cpu  100 0 100 700 100 0 0 0 0 0\n", "cpu  200 0 100 800 100 0 0 0 0 0\n"])
            (proc / "stat").write_text(next(samples))
            stats = bp.system_stats(proc, sleep=lambda _: (proc / "stat").write_text(next(samples)))
        self.assertEqual(stats["cpu_model"], "AMD EPYC 7763")
        self.assertAlmostEqual(stats["cpu_percent"], 50.0)
        self.assertEqual(stats["mem_used"], 4000000 * 1024)
        self.assertEqual(stats["swap_used"], 0)

    def test_without_proc_everything_is_unknown_and_says_why(self):
        stats, err = quiet(bp.system_stats, Path("/definitely/not/proc"), sleep=lambda _: None)
        self.assertIsNone(stats["cpu_percent"])
        self.assertIsNone(stats["mem_total"])
        self.assertIn("system stats unavailable", err)

    def test_short_cpu(self):
        self.assertEqual(bp.short_cpu("Intel(R) Xeon(R) Platinum 8370C CPU @ 2.80GHz"), "Intel Xeon Platinum 8370C")


class DataFilesTest(unittest.TestCase):
    def test_quote_changes_every_day_and_cycles(self):
        quotes = ["a", "b", "c"]
        days = [dt.date(2026, 9, 27) + dt.timedelta(days=i) for i in range(6)]
        picked = [bp.pick_quote(quotes, day) for day in days]
        self.assertEqual(sorted(picked[:3]), quotes)
        self.assertEqual(picked[:3], picked[3:])

    def test_every_quote_fits_the_card(self):
        quotes = bp.load_quotes(ROOT / "data" / "quotes.txt")
        self.assertGreater(len(quotes), 30)
        for quote in quotes:
            self.assertLessEqual(len(textwrap.wrap(quote, 84)), 2, quote)

    def test_pixel_grid(self):
        rows = bp.load_pixels(ROOT / "data" / "botyara.txt")
        self.assertEqual({len(row) for row in rows}, {40})
        self.assertEqual(len(bp.clusters(rows, "D")), 3)

    def test_empty_quotes_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quotes.txt"
            path.write_text("# only a comment\n\n")
            with self.assertRaises(ValueError):
                bp.load_quotes(path)

    def test_bad_pixel_grids_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "grid.txt"
            path.write_text("# comment\nWW\nW\n")
            with self.assertRaises(ValueError):
                bp.load_pixels(path)
            path.write_text("WQ\nWW\n")
            with self.assertRaises(ValueError):
                bp.load_pixels(path)


class TypingTest(unittest.TestCase):
    def test_card_grows_to_fit_long_lines(self):
        card = bp.render_typing(["x" * 60], ROOT / "fonts")
        width = int(ET.fromstring(card).get("width"))
        self.assertGreaterEqual(width, 60 * 24 * 0.6)

    def test_needs_at_least_one_line(self):
        with self.assertRaises(ValueError):
            bp.render_typing([], ROOT / "fonts")


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for folder in ("data", "fonts"):
            shutil.copytree(ROOT / folder, self.root / folder)
        (self.root / "assets").mkdir()
        shutil.copy(ROOT / "assets" / "botyara-avatar.png", self.root / "assets")
        shutil.copy(FIXTURE, self.root / "data" / "snapshot.json")
        self.snapshot = json.loads(FIXTURE.read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def card(self, name):
        path = self.root / "assets" / name
        ET.parse(path)  # well-formed XML, or this raises
        return path.read_text(encoding="utf-8")

    def test_offline_build_renders_every_card(self):
        quiet(bp.build, self.root, offline=True, now=NOW, system=lambda: SYSTEM)
        neofetch = self.card("generated/neofetch.svg")
        for text in (
            "6 лет, 1 месяц, 28 дней",
            "backseat",
            "пуш сегодня",
            "Python 93%",
            "12% · AMD EPYC 7763 ×4",
            "2.0 / 16.0 GB",
            "снимок от 2026-09-27",
        ):
            self.assertIn(text, neofetch)
        self.assertNotIn("Активность", neofetch)  # unknown in the snapshot, so the row is skipped
        says = self.card("generated/botyara-says.svg")
        self.assertIn("data:image/png;base64,", says)
        self.assertIn(bp.esc(bp.pick_quote(bp.load_quotes(self.root / "data" / "quotes.txt"), NOW.date())), says)
        self.assertIn("Делаю ботов, которые всё помнят", self.card("typing.svg"))
        self.card("wave.svg")
        self.assertIn("змейка вылупится", self.card("generated/snake-dark.svg"))
        self.assertEqual(json.loads((self.root / "data" / "snapshot.json").read_text()), self.snapshot)

    def test_live_build_saves_the_snapshot(self):
        live = dict(self.snapshot, source="GitHub API", contributions_last_year=321)
        quiet(bp.build, self.root, now=NOW, fetch=lambda *args, **kwargs: live, system=lambda: SYSTEM)
        self.assertEqual(json.loads((self.root / "data" / "snapshot.json").read_text())["contributions_last_year"], 321)
        neofetch = self.card("generated/neofetch.svg")
        self.assertIn("321 контрибуция за год", neofetch)
        self.assertIn("живая статистика GitHub", neofetch)

    def test_api_failure_falls_back_to_the_snapshot(self):
        def broken(*args, **kwargs):
            raise OSError("rate limited")

        _, err = quiet(bp.build, self.root, now=NOW, fetch=broken, system=lambda: SYSTEM)
        self.assertIn("rate limited", err)
        self.assertIn("снимок от 2026-09-27", self.card("generated/neofetch.svg"))

    def test_real_snake_is_never_replaced_by_the_placeholder(self):
        generated = self.root / "assets" / "generated"
        generated.mkdir()
        (generated / "snake-dark.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
        quiet(bp.build, self.root, offline=True, now=NOW, system=lambda: SYSTEM)
        self.assertEqual((generated / "snake-dark.svg").read_text(), "<svg xmlns='http://www.w3.org/2000/svg'/>")
        self.assertIn("змейка вылупится", self.card("generated/snake-light.svg"))

    def test_unknown_system_stats_say_na(self):
        unknown = dict.fromkeys(SYSTEM)
        quiet(bp.build, self.root, offline=True, now=NOW, system=lambda: unknown)
        neofetch = self.card("generated/neofetch.svg")
        self.assertIn(">н/д<", neofetch)
        self.assertIn(">выкл<", neofetch)


if __name__ == "__main__":
    unittest.main()
