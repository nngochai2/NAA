from jenkins_mcp.config import JenkinsConfig


def _cfg(**kw):
    return JenkinsConfig(url="u", ssl_verify=True, timeout=1.0, **kw)


def test_all_tools_enabled_by_default():
    assert _cfg().is_tool_enabled("jenkins_delete_job")


def test_block_list_disables_listed_tools():
    cfg = _cfg(block_tools=frozenset({"jenkins_delete_job"}))
    assert not cfg.is_tool_enabled("jenkins_delete_job")
    assert cfg.is_tool_enabled("jenkins_get_job_status")


def test_allow_list_wins_over_block_list():
    cfg = _cfg(allow_tools=frozenset({"jenkins_get_job_status"}), block_tools=frozenset({"jenkins_get_job_status"}))
    assert cfg.is_tool_enabled("jenkins_get_job_status")
    assert not cfg.is_tool_enabled("jenkins_list_jobs")
