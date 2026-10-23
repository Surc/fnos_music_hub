"""One stable namespace for each user's private native runtime."""

import hashlib


def engine_directory(settings, user_guid):
    namespace = hashlib.sha256(
        (settings.instance_id + "\0" + user_guid).encode()
    ).hexdigest()[:32]
    return settings.data_dir / "engines" / namespace
