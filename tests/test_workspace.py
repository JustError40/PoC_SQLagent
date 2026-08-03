from sqlagent.workspace import Workspace


def test_workspace_is_git_versioned(tmp_path) -> None:
    workspace = Workspace(tmp_path / "skill")
    workspace.write_text("SKILL.md", "hello\n")
    first = workspace.commit("init skill")
    assert first
    assert workspace.current_branch() == "main"
    branch = workspace.create_candidate("test")
    assert branch == "evolution/test"
    workspace.write_text("experience/note.md", "candidate\n")
    second = workspace.commit("candidate mutation")
    assert second != first

