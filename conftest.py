import pytest


def pytest_addoption(parser):
    parser.addoption("--headed", action="store_true", default=False)


@pytest.fixture
def headed(request):
    return request.config.getoption("--headed")
