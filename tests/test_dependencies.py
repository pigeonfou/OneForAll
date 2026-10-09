import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "oneforall"))
import dependencies

class DependencyTests(unittest.TestCase):
    def test_cpu_lock_removes_gpu_only_packages_and_keeps_versions(self):
        text, torch = dependencies.cpu_requirements("torch==2.14.1\nnvidia-cudnn-cu13==9.24\ncuda-bindings==13.4\ntriton==3.8\ntransformers==5.18\n")
        self.assertEqual(text, "torch==2.14.1\ntransformers==5.18\n")
        self.assertEqual(torch, "torch==2.14.1")
        with self.assertRaises(ValueError): dependencies.cpu_requirements("--extra-index-url https://example.com\ntorch==2.14.1")
    def test_same_dependencies_reused_code_is_separate_and_abi_changes_pool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); commands = []; abi = ["python-test-abi"]
            def execute(app, *args, **kwargs):
                commands.append(tuple(map(str, args)))
                if args[0] == "python3" and args[1] == "-c": return abi[0]
                if "venv" in args:
                    Path(args[-1]).mkdir(parents=True, exist_ok=True)
                if kwargs.get("capture"):
                    site = Path(args[0]).parent.parent / "lib/site-packages"
                    site.mkdir(parents=True, exist_ok=True)
                    return str(site)
                return ""
            def release(name, version="1"):
                path = root / name; path.mkdir()
                (path / "requirements.lock").write_text("torch==2.14.1\ntransformers==" + version + "\n")
                return path
            with patch.object(dependencies, "OPT", root), patch.object(dependencies, "as_user", side_effect=execute), patch.object(dependencies, "run"):
                first = dependencies.prepare_doctrad_environment(release("first"), root)
                initial = len([c for c in commands if "--index-url" in c])
                second = dependencies.prepare_doctrad_environment(release("second"), root)
                self.assertEqual(first, second)
                self.assertEqual(initial, len([c for c in commands if "--index-url" in c]))
                self.assertIn(str(first / "lib/site-packages"), (root / "second/.venv/lib/site-packages/oneforall-dependencies.pth").read_text())
                third = dependencies.prepare_doctrad_environment(release("third", "2"), root)
                self.assertNotEqual(first, third)
                abi[0] = "new-abi"
                fourth = dependencies.prepare_doctrad_environment(release("fourth"), root)
                self.assertNotEqual(first, fourth)
                installs = [c for c in commands if c[-1] in (str(root/"first"), str(root/"second")) and "install" in c]
                self.assertEqual(len(installs), 2)
                self.assertTrue(all("--no-deps" in c and "--no-build-isolation" in c for c in installs))
    def test_failure_never_marks_pool_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); release=root/"release";release.mkdir()
            (release/"requirements.lock").write_text("torch==2.14.1\n")
            def execute(app,*args,**kwargs):
                if kwargs.get("capture"):return "abi"
                if "--index-url" in args: raise ValueError("CPU wheel absent")
            with patch.object(dependencies,"OPT",root),patch.object(dependencies,"as_user",side_effect=execute),patch.object(dependencies,"run"):
                with self.assertRaises(ValueError): dependencies.prepare_doctrad_environment(release,root)
            self.assertFalse(list((root/"apps/doctrad/dependencies").glob("*/.ready")))
