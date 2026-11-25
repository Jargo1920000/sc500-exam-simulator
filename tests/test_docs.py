"""Offline checks for how docs.py picks a Learn page. Run: python3 tests/test_docs.py (or pytest)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import docs  # noqa: E402

L = "https://learn.microsoft.com/en-us"


def pick(term, *pages):
    return docs._pick([{"url": u, "title": t} for u, t in pages], ("url",), ("title",), term)


def test_skips_hubs_study_guides_and_videos():
    for url in (f"{L}/entra/identity/", f"{L}/credentials/certifications/resources/study-guides/sc-500",
                f"{L}/azure/defender-for-cloud/episode-twenty", f"{L}/shows/x/y"):
        assert not docs._good(url), url
    assert docs._good(f"{L}/azure/defender-for-cloud/enable-just-in-time-access")


def test_best_title_match_beats_search_order():
    hit = pick("Enable just-in-time access on VMs",
               (f"{L}/windows/security/application-control", "Application Control for Windows"),
               (f"{L}/azure/defender-for-cloud/enable-just-in-time-access", "Enable just-in-time access on VMs"))
    assert hit["url"].endswith("enable-just-in-time-access")


def test_weak_match_is_not_exact():
    # Shares only "entra" and "authentication" (half of 4 topic words), and product folders don't count.
    assert pick("Azure SQL Microsoft Entra-only authentication",
                (f"{L}/entra/identity/authentication/howto-authentication-passwordless-security-key",
                 "Passwordless security key sign-in - Microsoft Entra ID")) is None


def test_docs_beat_training_on_a_tie():
    hit = pick("Defender for Containers overview",
               (f"{L}/training/modules/defender-containers-overview", "Defender for Containers overview"),
               (f"{L}/azure/defender-for-cloud/defender-for-containers-overview", "Defender for Containers overview"))
    assert "/training/" not in hit["url"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("docs tests passed")
