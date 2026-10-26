'''The Lambda layer: it must always answer with something JSON serializable.'''
import json
from types import SimpleNamespace

from src import lambda_function
from src.run_report import ProcessingReport, ProcessingResult, ProcessingStep, RunReport
from tests.factories import make_grant, make_request

CONTEXT = SimpleNamespace(function_name='access-manager', aws_request_id='test-request')


class FakeManager:
    def __init__(self, report=None, error=None):
        self._report, self._error = report or RunReport(), error

    def run(self):
        if self._error:
            raise self._error
        return self._report


def use_manager(monkeypatch, manager):
    monkeypatch.setattr(lambda_function, 'AccessManager', lambda: manager)


def sample_report():
    report = RunReport()
    report.extend([
        ProcessingReport.ok(make_request(), ProcessingStep.REQUEST_ROUTING, ProcessingResult.NO_ACTION_NEEDED),
        ProcessingReport.ok(make_grant(), ProcessingStep.PROVISION_GRANT, ProcessingResult.NOTIFICATION_REQUIRED),
        ProcessingReport.failed(make_grant(), ProcessingStep.REVOKE_GRANT, 'Okta is down'),
    ])
    return report


def test_a_successful_run_answers_200(monkeypatch):
    use_manager(monkeypatch, FakeManager(sample_report()))

    response = lambda_function.lambda_handler({}, CONTEXT)

    assert response['statusCode'] == 200
    assert response['body']['message']


def test_the_response_can_be_serialized_to_json(monkeypatch):
    # Lambda has to serialize whatever we return.
    use_manager(monkeypatch, FakeManager(sample_report()))

    response = lambda_function.lambda_handler({}, CONTEXT)

    json.dumps(response)


def test_the_response_summarizes_the_run(monkeypatch):
    use_manager(monkeypatch, FakeManager(sample_report()))

    body = lambda_function.lambda_handler({}, CONTEXT)['body']

    assert body['results'] == {'total': 3, 'failed': 1}


def test_a_run_with_failures_is_still_a_successful_invocation(monkeypatch):
    # Failures are reported to the IAM team; retrying the whole Lambda would not help.
    use_manager(monkeypatch, FakeManager(sample_report()))

    assert lambda_function.lambda_handler({}, CONTEXT)['statusCode'] == 200


def test_an_unexpected_error_answers_500_with_the_reason(monkeypatch):
    use_manager(monkeypatch, FakeManager(error=RuntimeError('kaboom')))

    response = lambda_function.lambda_handler({}, CONTEXT)

    assert response['statusCode'] == 500
    assert 'kaboom' in response['body']['error']
    json.dumps(response)


def test_a_manager_that_cannot_be_created_answers_500(monkeypatch):
    def broken():
        raise RuntimeError('no AWS region configured')

    monkeypatch.setattr(lambda_function, 'AccessManager', broken)

    response = lambda_function.lambda_handler({}, CONTEXT)

    assert response['statusCode'] == 500


def test_a_minimal_context_is_enough(monkeypatch):
    # `make run` invokes the handler with a context that only has aws_request_id.
    use_manager(monkeypatch, FakeManager())
    minimal = SimpleNamespace(aws_request_id='local-test')

    assert lambda_function.lambda_handler({'test': 'data'}, minimal)['statusCode'] == 200
