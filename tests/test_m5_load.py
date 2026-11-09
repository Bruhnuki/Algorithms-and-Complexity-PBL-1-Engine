"""10 virtual players each play a full sprint at once (mock model). Real-GPU numbers come from tools/m0_bench.py."""
import threading
import time

import pytest

from api_helpers import Driver, Env, mock_client, new_run
from fixit import bot
from fixit.gateway.gateway import Gateway
from test_m3_gateway import GOOD, reply


@pytest.mark.load
def test_load_10_players(tmp_path, content):
    gw = Gateway(content, mock_client(reply(GOOD, delay=0.02)), slots=4)
    e = Env(tmp_path, content, gateway=gw)
    e.settings.dialogue_inline = False
    clients = [e.signup(f"p{i}@x.io") for i in range(10)]
    lat, errors = [], []
    script = bot.play(11, content, "coach_delegate").log

    def player(c):
        try:
            rid = new_run(c)
            d, since = Driver(c, rid), 0
            for cmd in script:
                t0 = time.perf_counter()
                r = d.cmd(cmd["type"], **cmd["payload"])
                lat.append(time.perf_counter() - t0)
                assert r.status_code == 200, r.text
                t0 = time.perf_counter()
                since = c.get(f"/api/v1/runs/{rid}/state", params={"since": since}).json()["seq"]
                time.sleep(0.15)  # a human polls at 1 Hz; this is still ~7x faster
                lat.append(time.perf_counter() - t0)
        except Exception as ex:  # noqa: BLE001
            errors.append(ex)

    threads = [threading.Thread(target=player, args=(c,)) for c in clients]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors[:2]
    lat.sort()
    p95 = lat[int(len(lat) * 0.95)]
    assert p95 < 0.15, f"p95={p95:.3f}s"
