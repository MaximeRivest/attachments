"""
Tests for GitHub sources - github:// and github.com repo-root handling.

=============================================================================
TEST GUIDELINES FOR GITHUB SOURCES
=============================================================================

GOOD tests for GitHub sources:
    - Test repo-root URL detection (only exact /owner/repo roots clone)
    - Test owner/repo validation (command-injection prevention)

BAD tests for GitHub sources:
    - Making real git clones (slow, network-dependent) — mock or skip

=============================================================================
"""

from __future__ import annotations

from attachments._sources.github import _is_github_repo_root_url


class TestIsGithubRepoRootUrl:
    """Tests for _is_github_repo_root_url."""

    def test_simple_repo_url(self):
        assert _is_github_repo_root_url("https://github.com/owner/repo") is True

    def test_repo_with_git_suffix(self):
        assert _is_github_repo_root_url("https://github.com/owner/repo.git") is True

    def test_repo_with_query_params(self):
        assert (
            _is_github_repo_root_url("https://github.com/owner/repo?ref=main") is True
        )

    def test_file_path_not_repo_root(self):
        assert (
            _is_github_repo_root_url("https://github.com/owner/repo/blob/main/file.py")
            is False
        )

    def test_non_github_url(self):
        assert _is_github_repo_root_url("https://gitlab.com/owner/repo") is False

    def test_http_not_https(self):
        assert _is_github_repo_root_url("http://github.com/owner/repo") is False
