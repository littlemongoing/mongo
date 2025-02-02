"""Unit tests for resmoke_tasks.py."""
import unittest

import inject
from mock import MagicMock

import buildscripts.task_generation.task_types.resmoke_tasks as under_test
from buildscripts.ciconfig.evergreen import EvergreenProjectConfig, Variant
from buildscripts.task_generation.resmoke_proxy import ResmokeProxyService
from buildscripts.task_generation.suite_split import GeneratedSuite, SubSuite
from buildscripts.task_generation.task_types.gentask_options import GenTaskOptions
from buildscripts.util.teststats import TestRuntime

# pylint: disable=missing-docstring,invalid-name,unused-argument,no-self-use,protected-access


class TestHelperMethods(unittest.TestCase):
    def test_string_contains_any_of_args(self):
        args = ["repeatSuites", "repeat"]
        string = "--suite=suite 0.yml --originSuite=suite resmoke_args --repeat=5"
        self.assertEqual(True, under_test.string_contains_any_of_args(string, args))

    def test_string_contains_any_of_args_for_empty_args(self):
        args = []
        string = "--suite=suite 0.yml --originSuite=suite resmoke_args --repeat=5"
        self.assertEqual(False, under_test.string_contains_any_of_args(string, args))

    def test_string_contains_any_of_args_for_non_matching_args(self):
        args = ["random_string_1", "random_string_2", "random_string_3"]
        string = "--suite=suite 0.yml --originSuite=suite resmoke_args --repeat=5"
        self.assertEqual(False, under_test.string_contains_any_of_args(string, args))


def build_mock_gen_options(use_default_timeouts=False, timeout_secs=None, exec_timeout_secs=None):
    return GenTaskOptions(create_misc_suite=True, is_patch=True, generated_config_dir="tmpdir",
                          use_default_timeouts=use_default_timeouts, timeout_secs=timeout_secs,
                          exec_timeout_secs=exec_timeout_secs)


def build_mock_gen_params(repeat_suites=1, resmoke_args="resmoke args"):
    return under_test.ResmokeGenTaskParams(
        use_large_distro=False,
        require_multiversion_setup=False,
        require_multiversion_version_combo=False,
        repeat_suites=repeat_suites,
        resmoke_args=resmoke_args,
        resmoke_jobs_max=None,
        large_distro_name=None,
        config_location="generated_config",
    )


def build_mock_suite(n_sub_suites, include_runtimes=True):
    return GeneratedSuite(
        sub_suites=[
            SubSuite(
                test_list=[f"test_{i*j}" for j in range(3)],
                runtime_list=[TestRuntime(test_name=f"test_{i*j}", runtime=3.14)
                              for j in range(3)] if include_runtimes else None, task_overhead=0)
            for i in range(n_sub_suites)
        ],
        build_variant="build variant",
        task_name="task name",
        suite_name="suite name",
    )


def build_mock_evg_project_config():
    tasks = [{"name": "task name"}]
    buildvariants = [{
        "name": "build variant",
        "tasks": tasks,
    }]
    project_conf = {
        "buildvariants": buildvariants,
        "tasks": tasks,
    }
    return EvergreenProjectConfig(project_conf)


class TestGenerateTask(unittest.TestCase):
    def setUp(self) -> None:
        def dependencies(binder: inject.Binder) -> None:
            binder.bind(ResmokeProxyService, ResmokeProxyService())

        inject.clear_and_configure(dependencies)

    def test_evg_config_does_not_overwrite_repeatSuites_resmoke_arg_with_repeatSuites_default(self):
        mock_gen_options = build_mock_gen_options()
        params = build_mock_gen_params(resmoke_args="resmoke_args --repeatSuites=5")
        suites = build_mock_suite(1, include_runtimes=False)
        mock_evg_project_config = build_mock_evg_project_config()

        resmoke_service = under_test.ResmokeGenTaskService(mock_gen_options,
                                                           mock_evg_project_config)
        tasks = resmoke_service.generate_tasks(suites, params)

        for task in tasks:
            found_resmoke_cmd = False
            for cmd in task.shrub_task.commands:
                cmd_dict = cmd.as_dict()
                if cmd_dict.get("func") == "run generated tests":
                    found_resmoke_cmd = True
                    args = cmd_dict.get("vars", {}).get("resmoke_args")
                    self.assertIn("--repeatSuites=5", args)
                    self.assertNotIn("--repeatSuites=1", args)

            self.assertTrue(found_resmoke_cmd)

    def test_evg_config_does_not_overwrite_repeat_resmoke_arg_with_repeatSuites_default(self):
        mock_gen_options = build_mock_gen_options()
        params = build_mock_gen_params(resmoke_args="resmoke_args --repeat=5")
        suites = build_mock_suite(1, include_runtimes=False)
        mock_evg_project_config = build_mock_evg_project_config()

        resmoke_service = under_test.ResmokeGenTaskService(mock_gen_options,
                                                           mock_evg_project_config)
        tasks = resmoke_service.generate_tasks(suites, params)

        for task in tasks:
            found_resmoke_cmd = False
            for cmd in task.shrub_task.commands:
                cmd_dict = cmd.as_dict()
                if cmd_dict.get("func") == "run generated tests":
                    found_resmoke_cmd = True
                    args = cmd_dict.get("vars", {}).get("resmoke_args")
                    self.assertIn("--repeat=5", args)
                    self.assertNotIn("--repeatSuites=1", args)

            self.assertTrue(found_resmoke_cmd)

    def test_evg_config_has_timeouts_for_repeated_suites(self):
        n_sub_suites = 3
        mock_gen_options = build_mock_gen_options()
        params = build_mock_gen_params(repeat_suites=5)
        suites = build_mock_suite(n_sub_suites)
        mock_evg_project_config = build_mock_evg_project_config()

        resmoke_service = under_test.ResmokeGenTaskService(mock_gen_options,
                                                           mock_evg_project_config)
        tasks = resmoke_service.generate_tasks(suites, params)

        self.assertEqual(n_sub_suites + 1, len(tasks))
        for resmoke_task in tasks:
            task = resmoke_task.shrub_task
            if "misc" in task.name:
                # Misc tasks should use default timeouts.
                continue
            self.assertGreaterEqual(len(task.commands), 1)
            timeout_cmd = task.commands[0]
            self.assertEqual("timeout.update", timeout_cmd.command)

    def test_suites_without_enough_info_should_not_include_timeouts(self):
        mock_gen_options = build_mock_gen_options()
        params = build_mock_gen_params()
        suites = build_mock_suite(1, include_runtimes=False)
        mock_evg_project_config = build_mock_evg_project_config()

        resmoke_service = under_test.ResmokeGenTaskService(mock_gen_options,
                                                           mock_evg_project_config)
        tasks = resmoke_service.generate_tasks(suites, params)

        self.assertEqual(2, len(tasks))
        for task in tasks:
            for cmd in task.shrub_task.commands:
                cmd_dict = cmd.as_dict()
                self.assertNotEqual("timeout.update", cmd_dict.get("command"))

    def test_timeout_info_not_included_if_use_default_timeouts_set(self):
        mock_gen_options = build_mock_gen_options(use_default_timeouts=True)
        params = build_mock_gen_params()
        suites = build_mock_suite(1)
        mock_evg_project_config = build_mock_evg_project_config()

        resmoke_service = under_test.ResmokeGenTaskService(mock_gen_options,
                                                           mock_evg_project_config)
        tasks = resmoke_service.generate_tasks(suites, params)

        self.assertEqual(2, len(tasks))
        for task in tasks:
            for cmd in task.shrub_task.commands:
                cmd_dict = cmd.as_dict()
                self.assertNotEqual("timeout.update", cmd_dict.get("command"))

    def test_suites_without_enough_info_should_inherit_bv_timeouts_if_specified(self):
        mock_gen_options = build_mock_gen_options(timeout_secs=300, exec_timeout_secs=150)
        params = build_mock_gen_params()
        suites = build_mock_suite(1, include_runtimes=False)
        mock_evg_project_config = build_mock_evg_project_config()

        resmoke_service = under_test.ResmokeGenTaskService(mock_gen_options,
                                                           mock_evg_project_config)
        tasks = resmoke_service.generate_tasks(suites, params)

        self.assertEqual(2, len(tasks))
        for resmoke_task in tasks:
            task = resmoke_task.shrub_task
            self.assertGreaterEqual(len(task.commands), 1)
            timeout_cmd = task.commands[0]
            self.assertEqual("timeout.update", timeout_cmd.command)
            self.assertEqual(300, timeout_cmd.params["timeout_secs"])
            self.assertEqual(150, timeout_cmd.params["exec_timeout_secs"])
