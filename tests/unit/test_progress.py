from refcheck.ui.progress import ProgressEvent, ProgressReporter, Stage


def test_reporter_collects_events():
    events: list[ProgressEvent] = []
    reporter = ProgressReporter(callback=events.append)

    reporter.start(Stage.EXTRACT, total=10, message="참고문헌 파싱")
    reporter.update(Stage.EXTRACT, current=5)
    reporter.finish(Stage.EXTRACT)

    assert len(events) == 3
    assert events[0].stage == Stage.EXTRACT
    assert events[0].total == 10
    assert events[0].current == 0
    assert events[1].current == 5
    assert events[2].current == 10  # finish sets current=total


def test_reporter_noop_callback_does_not_raise():
    # None callback → reports are no-ops (safe for library code)
    reporter = ProgressReporter(callback=None)
    reporter.start(Stage.VERIFY_METADATA, total=5)
    reporter.update(Stage.VERIFY_METADATA, current=3)
    reporter.finish(Stage.VERIFY_METADATA)
    # no exceptions


def test_stage_labels_are_korean():
    assert "파싱" in Stage.EXTRACT.label or "추출" in Stage.EXTRACT.label
    assert "메타데이터" in Stage.VERIFY_METADATA.label
