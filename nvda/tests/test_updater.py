import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


def load_updater():
	modules = {name: types.ModuleType(name) for name in (
		"addonHandler", "config", "globalVars", "gui", "wx", "core", "logHandler", "systemUtils",
	)}
	modules["core"].callLater = Mock()
	modules["logHandler"].log = Mock()
	modules["systemUtils"].ExecAndPump = Mock()
	modules["gui"].ExecAndPump = Mock()
	root = Path(__file__).resolve().parents[1] / "addon/globalPlugins"
	path = root / "apolloJuno/_updater.py"
	spec = importlib.util.spec_from_file_location("apollo_updater_test", path)
	module = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, modules):
		spec.loader.exec_module(module)
	module._ = lambda text: text
	return module


updater = load_updater()
# Public signature for the five-byte test payload; tests need no signing key.
SIGNED_FIXTURE = "qgF40d+7GnJ1rCBhh4G8z4rCuUH2gOUss6DbHx2iBT1jKWuVd74JtUSxLmegNCamdQTox1IOn/YFHx9Gb47sLo7DHXIonxjX1W906JQymGrHA++kWaELc4BjHAvJp+cobVnMR8++csuhossXKfpXk5AvYUWH1iRDUTzDYYIR5W1WYM1lopzTgk5Agz2hpWhkE8mAdmsUrKtOHqEgpKODXcKW7hpGiIk2YfhacQp5xXV09aUoV3JusGEj5DS8pBkkJ2KsQzyVBkePd1F945UCpD4ihA/ji/d0u5W8G4YgSMBWARdVjlawoKhdNmnOtC0vqeZqE+mGNBeVgGOWMhWFlKjk/t80z/0z4AH0L5Q0rw+JAlZSPNW/mHMC3d4DicOj9bIkxI0cFQGC0nYaFHWr6Qul4srKIDD0TW+6eSIaE7+cH0oU8eWneq53Ub5vkNZeEsZHO2HkOayjWg7BGMpD9Q3V4PWkWa/gva291OxG9VD8zZiXnWvKyb87qIOOTlqE"


class UpdaterTests(unittest.TestCase):
	def info(self):
		return {
			"addon": "apolloJuno", "version": "1.1.1",
			"url": "https://github.com/OnjLouis/apolloJuno/releases/download/v1.1.1/apolloJuno-1.1.1.nvda-addon",
			"sha256": hashlib.sha256(b"hello").hexdigest(), "size": 5,
		}

	def test_unsigned_manifest_is_rejected(self):
		with self.assertRaises(RuntimeError):
			updater._verifyManifest(self.info())

	def signed_info(self):
		info = self.info()
		info["signature"] = SIGNED_FIXTURE
		return info

	def test_valid_signature_is_accepted(self):
		updater._verifyManifest(self.signed_info())

	def test_signature_protects_every_update_field(self):
		for key, value in (("addon", "samsungTVVoices"), ("version", "1.1.2"), ("url", "https://example.invalid"), ("size", 6), ("sha256", "0" * 64)):
			with self.subTest(key=key):
				info = self.signed_info()
				info[key] = value
				with self.assertRaises(RuntimeError):
					updater._verifyManifest(info)

	def test_bad_signature_encoding_length_and_value_are_rejected(self):
		modulus = base64.b64decode(updater.PUBLIC_MODULUS)
		for value in (None, "!", base64.b64encode(b"short").decode(), base64.b64encode(modulus).decode()):
			with self.subTest(value=value):
				info = self.info()
				info["signature"] = value
				with self.assertRaises(RuntimeError):
					updater._verifyManifest(info)

	def test_signed_metadata_contract_rejects_foreign_or_invalid_fields(self):
		for key, value in (("addon", "samsungGalaxyVoices"), ("version", "../evil"), ("url", "https://example.invalid"), ("size", True), ("size", 0), ("size", updater.MAX_PACKAGE_SIZE + 1), ("sha256", "bad")):
			with self.subTest(key=key, value=value), patch.object(updater.hmac, "compare_digest", return_value=True):
				info = self.signed_info()
				info[key] = value
				with self.assertRaises(RuntimeError):
					updater._verifyManifest(info)

	def test_release_lookup_uses_signed_manifest_not_cli_asset(self):
		info = self.signed_info()
		url = "https://github.com/OnjLouis/apolloJuno/releases/download/v1.1.1/apolloJuno-update.json"
		release = {"tag_name": "v1.1.1", "assets": [
			{"name": "Prose2000-CLI-1.1.0.zip"},
			{"name": "apolloJuno-update.json", "browser_download_url": url},
		]}
		instance = object.__new__(updater.GitHubReleaseUpdater)
		instance.apiUrl = "https://api.github.com/repos/OnjLouis/apolloJuno/releases/latest"
		with patch.object(updater.urllib.request, "urlopen", side_effect=[io.BytesIO(json.dumps(release).encode()), io.BytesIO(json.dumps(info).encode())]):
			result = instance._getUpdateInfo()
		self.assertEqual(result["name"], "apolloJuno-1.1.1.nvda-addon")
		self.assertEqual(result["url"], info["url"])
		self.assertEqual(result["sha256"], info["sha256"])

	def test_unsigned_release_fails_closed(self):
		instance = object.__new__(updater.GitHubReleaseUpdater)
		instance.apiUrl = "https://api.github.com/repos/OnjLouis/apolloJuno/releases/latest"
		with patch.object(updater.urllib.request, "urlopen", return_value=io.BytesIO(b'{"tag_name":"v1.1.1","assets":[]}')):
			with self.assertRaises(RuntimeError):
				instance._getUpdateInfo()

	def test_release_tag_must_match_signed_version(self):
		release = {"tag_name": "v1.1.2", "assets": [{"name": "apolloJuno-update.json", "browser_download_url": "https://github.com/OnjLouis/apolloJuno/releases/download/v1.1.2/apolloJuno-update.json"}]}
		instance = object.__new__(updater.GitHubReleaseUpdater)
		instance.apiUrl = "https://api.github.com/repos/OnjLouis/apolloJuno/releases/latest"
		with patch.object(updater.urllib.request, "urlopen", side_effect=[io.BytesIO(json.dumps(release).encode()), io.BytesIO(json.dumps(self.signed_info()).encode())]):
			with self.assertRaises(RuntimeError):
				instance._getUpdateInfo()

	def test_wrong_signature_is_rejected(self):
		info = self.info()
		info["signature"] = base64.b64encode(b"\0" * 384).decode()
		with self.assertRaises(RuntimeError):
			updater._verifyManifest(info)

	def test_package_hash_and_size_are_checked(self):
		with tempfile.TemporaryDirectory() as directory:
			path = Path(directory) / "package"
			path.write_bytes(b"hello")
			updater._verifyDownload(path, self.info())
			for data in (b"HELLO", b"hell", b"hello!"):
				path.write_bytes(data)
				with self.assertRaises(RuntimeError):
					updater._verifyDownload(path, self.info())

	def test_download_cannot_exceed_the_signed_size(self):
		remote = io.BytesIO(b"too much data")
		remote.headers = {}
		with tempfile.TemporaryDirectory() as directory, patch.object(updater.urllib.request, "urlopen", return_value=remote):
			with self.assertRaises(RuntimeError):
				updater._downloadFile("https://example.invalid", str(Path(directory) / "package"), maxSize=5)

	def test_current_addon_excludes_pending_install(self):
		pending = types.SimpleNamespace(name="apolloJuno", isPendingInstall=True)
		installed = types.SimpleNamespace(name="apolloJuno", isPendingInstall=False)
		updater.addonHandler.getAvailableAddons = Mock(return_value=[pending, installed])
		instance = object.__new__(updater.GitHubReleaseUpdater)
		instance.addonName = "apolloJuno"
		self.assertIs(instance._currentAddon(), installed)

	def run_install(self, directory, identity="apolloJuno", version="1.1.1", staged=True, cancelled=False, pending=False):
		instance = object.__new__(updater.GitHubReleaseUpdater)
		instance.addonName = "apolloJuno"
		instance.updatesDir = directory
		instance.stopped = False
		old = Mock()
		instance._currentAddon = Mock(return_value=old)
		bundle = types.SimpleNamespace(manifest={"name": identity, "version": version}, _installExceptions=[])
		incoming = Mock() if staged else None
		frame = Mock()
		gui = types.SimpleNamespace(mainFrame=frame, messageBox=Mock())
		wx = types.SimpleNamespace(ProgressDialog=Mock(return_value=Mock()))
		for constant in ("PD_CAN_ABORT", "PD_ELAPSED_TIME", "PD_REMAINING_TIME", "PD_AUTO_HIDE", "OK", "ICON_ERROR"):
			setattr(wx, constant, 1)
		installer = Mock(return_value=incoming)
		updater.addonHandler.getAvailableAddons = Mock(return_value=[
			types.SimpleNamespace(name="apolloJuno", isPendingInstall=True)
		] if pending else [])
		def download(url, destination, update, max_size):
			Path(destination).write_bytes(b"hello")
			return not cancelled
		def run(function, *args):
			return types.SimpleNamespace(funcRes=function(*args))
		info = self.info()
		info["name"] = "apolloJuno-1.1.1.nvda-addon"
		with patch.object(updater, "gui", gui), patch.object(updater, "wx", wx), patch.object(updater, "ExecAndPump", run), patch.object(updater, "_downloadFile", download), patch.object(updater.addonHandler, "AddonBundle", Mock(return_value=bundle), create=True), patch.object(updater.addonHandler, "installAddonBundle", installer, create=True), patch.object(updater, "promptUserForRestart", Mock()):
			instance._downloadAndInstall(info)
		self.assertFalse((Path(directory) / info["name"]).exists())
		return old, incoming, installer

	def test_verified_package_is_staged_and_temporary_download_removed(self):
		with tempfile.TemporaryDirectory() as directory:
			old, incoming, installer = self.run_install(directory)
		installer.assert_called_once()
		old.requestRemove.assert_called_once_with()
		incoming._cleanupAddonImports.assert_called_once_with()

	def test_wrong_package_identity_or_version_never_replaces_old_copy(self):
		for identity, version in (("samsungTVVoices", "1.1.1"), ("apolloJuno", "1.1.2")):
			with self.subTest(identity=identity, version=version), tempfile.TemporaryDirectory() as directory:
				old, _, installer = self.run_install(directory, identity=identity, version=version)
			installer.assert_not_called()
			old.requestRemove.assert_not_called()

	def test_failed_staging_preserves_installed_copy(self):
		with tempfile.TemporaryDirectory() as directory:
			old, _, installer = self.run_install(directory, staged=False)
		installer.assert_called_once()
		old.requestRemove.assert_not_called()

	def test_cancelled_download_preserves_installed_copy_and_cleans_partial(self):
		with tempfile.TemporaryDirectory() as directory:
			old, _, installer = self.run_install(directory, cancelled=True)
		installer.assert_not_called()
		old.requestRemove.assert_not_called()

	def test_pending_operation_blocks_a_second_install(self):
		with tempfile.TemporaryDirectory() as directory:
			old, _, installer = self.run_install(directory, pending=True)
		installer.assert_not_called()
		old.requestRemove.assert_not_called()

	def test_unknown_download_length_can_still_cancel(self):
		remote = io.BytesIO(b"hello")
		remote.headers = {}
		cancel = Mock(return_value=True)
		with tempfile.TemporaryDirectory() as directory, patch.object(updater.urllib.request, "urlopen", return_value=remote):
			self.assertFalse(updater._downloadFile("https://example.invalid", str(Path(directory) / "part"), cancel))
		cancel.assert_called_once_with(0)

	def test_never_cancels_the_timer(self):
		instance = object.__new__(updater.GitHubReleaseUpdater)
		instance.stopped = False
		instance.timer = Mock()
		previous = instance.timer
		instance.setInterval("never")
		previous.Stop.assert_called_once()
		self.assertIsNone(instance.timer)

	def test_hourly_and_daily_schedule_their_intervals(self):
		for interval, delay in (("hourly", 3600000), ("daily", 86400000)):
			instance = object.__new__(updater.GitHubReleaseUpdater)
			instance.stopped = False
			instance.timer = None
			instance.interval = interval
			instance.state = {"lastCheck": 1000}
			with patch.object(updater.time, "time", return_value=1), patch.object(updater, "callLater") as later:
				instance._scheduleNext()
			later.assert_called_once_with(delay, instance.checkNow, False)

	def test_stopped_check_never_starts_a_worker(self):
		instance = object.__new__(updater.GitHubReleaseUpdater)
		instance.stopped = True
		with patch.object(updater.threading, "Thread") as thread:
			instance.checkNow()
		thread.assert_not_called()

	def test_stopped_result_does_not_prompt(self):
		instance = object.__new__(updater.GitHubReleaseUpdater)
		instance.stopped = True
		with patch.object(updater.gui, "messageBox", create=True) as message:
			instance._handleCheck(True, self.info(), None)
		message.assert_not_called()

	def test_initial_release_version_has_equivalent_zero_patch(self):
		self.assertEqual(updater._parseVersion("1.0"), updater._parseVersion("1.0.0"))

	def test_unpublished_repository_has_no_update(self):
		instance = object.__new__(updater.GitHubReleaseUpdater)
		instance.apiUrl = "https://api.github.com/repos/OnjLouis/apolloJuno/releases/latest"
		error = updater.urllib.error.HTTPError(instance.apiUrl, 404, "Not Found", {}, None)
		with patch.object(updater.urllib.request, "urlopen", side_effect=error):
			self.assertIsNone(instance._getUpdateInfo())

	def test_oversized_metadata_is_rejected(self):
		instance = object.__new__(updater.GitHubReleaseUpdater)
		instance.apiUrl = "https://api.github.com/repos/OnjLouis/apolloJuno/releases/latest"
		with patch.object(updater.urllib.request, "urlopen", return_value=io.BytesIO(b" " * (updater.MAX_MANIFEST_SIZE + 1))):
			with self.assertRaises(RuntimeError):
				instance._getUpdateInfo()

	def test_corrupt_or_future_check_state_is_ignored(self):
		with tempfile.TemporaryDirectory() as directory:
			instance = object.__new__(updater.GitHubReleaseUpdater)
			instance.stateFile = str(Path(directory) / "state.json")
			for value in ([], {"lastCheck": "oops"}, {"lastCheck": -1}, {"lastCheck": 10**30}):
				Path(instance.stateFile).write_text(json.dumps(value))
				self.assertEqual(instance._loadState(), {"lastCheck": 0})


if __name__ == "__main__":
	unittest.main()
