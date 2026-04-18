from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from services import storage


class _FakeBlob:
    def __init__(self, objects: dict[str, set[str]], bucket_name: str, name: str):
        self._objects = objects
        self._bucket = bucket_name
        self.name = name

    def exists(self) -> bool:
        return self.name in self._objects.get(self._bucket, set())

    def delete(self) -> None:
        self._objects.setdefault(self._bucket, set()).discard(self.name)


class _FakeBucket:
    def __init__(self, objects: dict[str, set[str]], name: str):
        self._objects = objects
        self._name = name

    def blob(self, key: str) -> _FakeBlob:
        return _FakeBlob(self._objects, self._name, key)


class _FakeClient:
    def __init__(self, objects: dict[str, set[str]]):
        self._objects = objects

    def bucket(self, bucket_name: str) -> _FakeBucket:
        self._objects.setdefault(bucket_name, set())
        return _FakeBucket(self._objects, bucket_name)

    def list_blobs(self, bucket_name: str, prefix: str = "", max_results: int | None = None):
        objects = sorted(
            name for name in self._objects.get(bucket_name, set())
            if name.startswith(prefix)
        )
        if max_results is not None:
            objects = objects[:max_results]
        return [_FakeBlob(self._objects, bucket_name, name) for name in objects]


def test_delete_image_related_files_removes_all_prefix_objects(monkeypatch) -> None:
    image_id = "img-123"
    objects = {
        "raw-images-geopublish": {
            f"{image_id}/original.jpg",
            f"{image_id}/debug.tmp",
            "other-image/original.jpg",
        },
        "processed-images-geopublish": {
            f"{image_id}/cog.tif",
            f"{image_id}/preview.png",
            "other-image/cog.tif",
        },
    }

    fake_client = _FakeClient(objects)
    monkeypatch.setattr(storage, "get_gcs", lambda: fake_client)

    result = storage.delete_image_related_files(
        image_id=image_id,
        original_key=f"{image_id}/original.jpg",
        processed_key=f"{image_id}/cog.tif",
    )

    assert result["image_id"] == image_id
    assert result["prefix"] == f"{image_id}/"
    assert result["deleted_objects"] == 4
    assert objects["raw-images-geopublish"] == {"other-image/original.jpg"}
    assert objects["processed-images-geopublish"] == {"other-image/cog.tif"}


def test_delete_image_related_files_deletes_legacy_non_prefix_keys(monkeypatch) -> None:
    image_id = "img-legacy"
    legacy_raw_key = "legacy/folder/original.jpg"
    objects = {
        "raw-images-geopublish": {
            legacy_raw_key,
            "other-image/original.jpg",
        },
        "processed-images-geopublish": {"other-image/cog.tif"},
    }

    fake_client = _FakeClient(objects)
    monkeypatch.setattr(storage, "get_gcs", lambda: fake_client)

    result = storage.delete_image_related_files(
        image_id=image_id,
        original_key=legacy_raw_key,
        processed_key=None,
    )

    assert result["deleted_objects"] == 1
    assert legacy_raw_key not in objects["raw-images-geopublish"]
    assert objects["raw-images-geopublish"] == {"other-image/original.jpg"}
    assert objects["processed-images-geopublish"] == {"other-image/cog.tif"}
