"""Contains global variables for use in the ADMET-AI website."""
import time

import pandas as pd

from admet_ai.web.app import app

USER_TO_PREDS: dict[str, pd.DataFrame] = {}
USER_TO_LAST_ACTIVITY: dict[str, float] = {}


def get_user_preds(user_id: str) -> pd.DataFrame:
    """Gets the user's predictions."""
    return USER_TO_PREDS.get(user_id, pd.DataFrame())


def set_user_preds(user_id: str, preds_df: pd.DataFrame) -> None:
    """Sets the user's predictions."""
    USER_TO_PREDS[user_id] = preds_df
    update_user_activity(user_id)


def update_user_activity(user_id: str) -> None:
    """Updates the user's last activity time."""
    USER_TO_LAST_ACTIVITY[user_id] = time.time()


def remove_inactive_users(max_idle_seconds: float, now: float | None = None) -> int:
    """Removes stored data for users idle longer than max_idle_seconds.

    :return: The number of users removed.
    """
    now = time.time() if now is None else now
    num_removed = 0
    for user_id, last_activity in list(USER_TO_LAST_ACTIVITY.items()):
        if now - last_activity > max_idle_seconds:
            USER_TO_PREDS.pop(user_id, None)
            USER_TO_LAST_ACTIVITY.pop(user_id, None)
            num_removed += 1

    return num_removed


def cleanup_storage() -> None:
    """Clean up storage by removing data from users that are no longer active."""
    print("Starting cleanup")

    while True:
        cleanup_frequency = app.config["SESSION_LIFETIME"]
        time.sleep(cleanup_frequency)
        num_removed = remove_inactive_users(cleanup_frequency)

        print(
            f"Cleanup removed data from {num_removed:,} users with {len(USER_TO_PREDS):,} users remaining."
        )
