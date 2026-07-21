import multiprocessing

from worktime.instance import InstanceGuard, stop_tracker


def _hold_guard(lock_path, pid_path, ready, release):
    guard = InstanceGuard(lock_path=lock_path, pid_path=pid_path)
    ready.put(guard.acquire())
    release.get(timeout=5)
    guard.release()


def test_guard_publishes_and_cleans_its_pid(tmp_path):
    pid_path = tmp_path / "runtime" / "worktime.pid"
    guard = InstanceGuard(tmp_path / "app.lock", pid_path, process_id=1234)

    assert guard.acquire()
    assert pid_path.read_text().strip() == "1234"

    guard.release()
    assert not pid_path.exists()


def test_duplicate_guard_is_rejected(tmp_path):
    lock_path = tmp_path / "app.lock"
    pid_path = tmp_path / "runtime" / "worktime.pid"
    ready = multiprocessing.Queue()
    release = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_hold_guard,
        args=(lock_path, pid_path, ready, release),
    )
    process.start()
    try:
        assert ready.get(timeout=5) is True
        assert InstanceGuard(lock_path, pid_path).acquire() is False
    finally:
        release.put(True)
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()


def test_acquire_replaces_stale_pid(tmp_path):
    pid_path = tmp_path / "runtime" / "worktime.pid"
    pid_path.parent.mkdir(parents=True)
    pid_path.write_text("999999\n")
    guard = InstanceGuard(tmp_path / "app.lock", pid_path, process_id=4321)

    assert guard.acquire()
    assert pid_path.read_text().strip() == "4321"
    guard.release()


def test_release_does_not_remove_another_process_identity(tmp_path):
    pid_path = tmp_path / "runtime" / "worktime.pid"
    guard = InstanceGuard(tmp_path / "app.lock", pid_path, process_id=1234)
    assert guard.acquire()
    pid_path.write_text("5678\n")

    guard.release()

    assert pid_path.read_text().strip() == "5678"


def test_stop_tracker_waits_for_final_flush():
    class FakeTracker:
        stopped = False

        def stop(self):
            self.stopped = True

    class FakeThread:
        timeout = None

        def join(self, timeout):
            self.timeout = timeout

        def is_alive(self):
            return False

    tracker = FakeTracker()
    thread = FakeThread()

    assert stop_tracker(tracker, thread, timeout=6)
    assert tracker.stopped
    assert thread.timeout == 6
