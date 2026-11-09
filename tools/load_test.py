"""10-player load check with a mock model: python tools/load_test.py   (asserts API p95 < 150 ms)."""
import pathlib
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from api_helpers import Driver, Env, mock_client, new_run  # noqa: E402
from fixit import bot  # noqa: E402
from fixit.gateway.gateway import Gateway  # noqa: E402
from fixit.rules import content as cm  # noqa: E402
from test_m3_gateway import GOOD, reply  # noqa: E402

c = cm.get()
gw = Gateway(c, mock_client(reply(GOOD, delay=0.02)), slots=4)
e = Env(pathlib.Path(tempfile.mkdtemp()), c, gateway=gw)
e.settings.dialogue_inline = False
clients = [e.signup(f"p{i}@x.io") for i in range(10)]
script = bot.play(11, c, "coach_delegate").log
lat = {"cmd": [], "state": []}


def player(cx):
    rid = new_run(cx)
    dr, since = Driver(cx, rid), 0
    for cmd in script:
        t0 = time.perf_counter()
        assert dr.cmd(cmd["type"], **cmd["payload"]).status_code == 200
        lat["cmd"].append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        since = cx.get(f"/api/v1/runs/{rid}/state", params={"since": since}).json()["seq"]
        lat["state"].append(time.perf_counter() - t0)
        time.sleep(0.15)  # a human polls at 1 Hz; this is ~7x faster


threads = [threading.Thread(target=player, args=(x,)) for x in clients]
[t.start() for t in threads]
[t.join() for t in threads]
worst = 0.0
for name, xs in lat.items():
    xs.sort()
    p95 = xs[int(len(xs) * 0.95)]
    worst = max(worst, p95)
    print(name, len(xs), "p50 ms", round(xs[len(xs) // 2] * 1000), "p95 ms", round(p95 * 1000), "max ms", round(xs[-1] * 1000))
print("LOAD", "PASS" if worst < 0.15 else "FAIL")
sys.exit(0 if worst < 0.15 else 1)
