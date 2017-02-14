# Copyright 2015 tsuru-pool-recycle-plugin authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

import os
import unittest
import json

from io import StringIO
from mock import patch, Mock, call
from pool_recycle import plugin
from pool_recycle.plugin import (MoveNodeContainersError, RemoveNodeFromPoolError,
                                 RemoveMachineFromIaaSError, NewNodeError)


class FakeTsuruPool(object):

    def __init__(self, pool, move_node_containers_error=False, remove_node_from_pool_error=False,
                 remove_machine_from_iaas_error=False, pre_provision_error=False,
                 raise_errors_on_call_counter=0):
        self.pool = pool
        self.nodes_on_pool = ['127.0.0.1', '10.10.1.1', '10.1.1.2']
        self.machines_on_pool = ['127.0.0.1', '10.10.1.1', '10.1.1.2']
        self.new_nodes = ['1.2.3.4', '5.6.7.8', '9.10.11.12']
        self.move_node_containers_error = move_node_containers_error
        self.remove_node_from_pool_error = remove_node_from_pool_error
        self.remove_machine_from_iaas_error = remove_machine_from_iaas_error
        self.pre_provision_error = pre_provision_error
        self.call_count = 0
        self.raise_errors_on_call_counter = raise_errors_on_call_counter

    def get_machines_templates(self):
        return ['templateA', 'templateB']

    def get_nodes(self):
        return list(self.nodes_on_pool)

    def get_machines(self):
        return list(self.machines_on_pool)

    def remove_node_from_pool(self, node):
        if self.remove_node_from_pool_error and self.call_count >= self.raise_errors_on_call_counter:
            raise RemoveNodeFromPoolError("error on node {}".format(node))
        self.call_count += 1
        self.nodes_on_pool.remove(node)

    def move_node_containers(self, node, new_node, cur_retry, max_retry, wait_timeout):
        if self.move_node_containers_error and self.call_count >= self.raise_errors_on_call_counter:
            raise MoveNodeContainersError("error moving {} to {}".format(node, new_node))
        self.call_count += 1
        return True

    def remove_machine_from_iaas(self, node):
        if self.remove_machine_from_iaas_error and self.call_count >= self.raise_errors_on_call_counter:
            raise RemoveMachineFromIaaSError("error removing node {} from IaaS".format(node))
        self.machines_on_pool.remove(node)
        self.call_count += 1
        return True

    def create_new_node(self, template):
        if self.pre_provision_error and self.call_count >= self.raise_errors_on_call_counter:
            raise NewNodeError("error adding new node on IaaS")
        new_node = self.new_nodes.pop(0)
        self.nodes_on_pool.append(new_node)
        self.machines_on_pool.append(new_node)
        self.call_count += 1
        return new_node

    def add_node_to_pool(self, node_url, docker_port, docker_scheme, metadata):
        self.nodes_on_pool.append(node_url)
        return True

    def get_machine_metadata_from_iaas(self, node):
        return {'id': '001122', 'metadata': {'bla': 'ble', 'xxx': 'yyy'}}

    def get_node_metadata(self, node):
        return {'bla': 'ble', 'xxx': 'yyy'}


class FakeURLopenResponse(StringIO):

    def __init__(self, *args):
        try:
            self.code = args[1]
        except IndexError:
            self.code = 200
            pass
        try:
            self.msg = args[2]
        except IndexError:
            self.msg = "OK"
            pass
        self.headers = {'content-type': 'text/plain; charset=utf-8'}
        StringIO.__init__(self, unicode(args[0]))

    def getcode(self):
        return self.code


class TsuruPoolTestCase(unittest.TestCase):

    def setUp(self):
        os.environ["TSURU_TARGET"] = "https://cloud.tsuru.io/"
        os.environ["TSURU_TOKEN"] = "abc123"
        self.patcher = patch('urllib2.urlopen')
        self.urlopen_mock = self.patcher.start()

    def test_missing_env_var(self):
        del os.environ['TSURU_TOKEN']
        self.assertRaisesRegexp(KeyError,
                                "TSURU_TARGET or TSURU_TOKEN envs not set",
                                plugin.TsuruPool, "foobar")

    @patch('tsuruclient.nodes.Manager.list')
    def test_get_nodes_from_pool(self, mock):
        docker_nodes_json = '''
{
    "machines": [
        {
            "Id": "f04388e3-02e0-46ec-93c8-9e5ba095eeb8",
            "Iaas": "cloudstack",
            "Status": "running",
            "Address": "10.10.34.221",
            "CreationParams": {
                "displayname": "machine_a",
                "pool": "foobar"
            }
        },
        {
            "Id": "c56ba117-cac2-4aba-b3c9-bc273ca79db0",
            "Iaas": "cloudstack",
            "Status": "running",
            "Address": "10.20.42.42",
            "CreationParams": {
                "displayname": "machine_b",
                "pool": "bilbo"
            }
        },
        {
            "Id": "c059bfb9-7323-41a4-96dc-a44b8c5d97da",
            "Iaas": "cloudstack",
            "Status": "running",
            "Address": "10.30.33.182",
            "CreationParams": {
                "displayname": "machine_c"
            }
        }
    ],
    "nodes": [
        {
            "Address": "http://10.2.25.169:4243",
            "Metadata": {
                "pool": "bilbo"
            },
            "Status": "waiting"
        },
        {
            "Address": "http://10.23.26.76:4243",
            "Metadata": {
                "pool": "foobar"
            },
            "Status": "waiting"
        },
        {
            "Address": "http://10.25.23.138:4243",
            "Metadata": {
                "LastSuccess": "2015-02-04T11:47:54-02:00",
                "pool": "foobar"
            },
            "Status": "ready"
        }
    ]
}
        '''
        mock.return_value = json.loads(docker_nodes_json)
        pool_handler = plugin.TsuruPool("foobar")
        self.assertListEqual(pool_handler.get_nodes(), ['http://10.23.26.76:4243',
                                                        'http://10.25.23.138:4243'])

        docker_nodes_null = '{ "machines": null, "nodes": null }'
        mock.return_value = json.loads(docker_nodes_null)
        self.assertListEqual(pool_handler.get_nodes(), [])

    @patch('tsuruclient.nodes.Manager.list')
    def test_get_node_metadata(self, mock):
        fake_response_iaas = '''{"machines":[{"Id": "abc", "Address": "10.10.2.1",
                                              "CreationParams": {"test": "abc"}}],
                                 "nodes":[{"Address": "http://10.20.1.2:4243",
                                           "Metadata": {"test": "cde"}}]}'''
        mock.return_value = json.loads(fake_response_iaas)
        pool_handler = plugin.TsuruPool("foobar")
        response_metadata = {u'test': u'cde'}
        self.assertEqual(pool_handler.get_node_metadata('http://10.20.1.2'), response_metadata)

    @patch('tsuruclient.nodes.Manager.list')
    def test_get_node_metadata_return_none(self, mock):
        fake_response_iaas = '''{"machines":[{"Id": "abc", "Address": "10.10.2.1",
                                              "CreationParams": {"test": "abc"}}],
                                 "nodes":[{"Address": "http://10.20.1.2:4243",
                                           "Metadata": {"test": "cde"}}]}'''
        mock.return_value = json.loads(fake_response_iaas)
        pool_handler = plugin.TsuruPool("foobar")
        self.assertEqual(pool_handler.get_node_metadata('http://10.20.20.2'), None)

    @patch('tsuruclient.nodes.Manager.list')
    def test_get_node_metadata_return_none_on_key_error(self, mock):
        fake_response_iaas = []
        mock.return_value = fake_response_iaas
        pool_handler = plugin.TsuruPool("foobar")
        self.assertEqual(pool_handler.get_node_metadata('http://10.20.20.2'), None)

    @patch('tsuruclient.machines.Manager.list')
    def test_get_machine_metadata_from_iaas(self, mock):
        fake_response_iaas = '''[{"Id": "abc", "Address": "10.10.2.1", "CreationParams": {"test": "abc"}},
                                {"Id": "def", "Address": "10.20.1.2", "CreationParams": {"test": "cde"}}]'''
        mock.return_value = json.loads(fake_response_iaas)
        pool_handler = plugin.TsuruPool("foobar")
        response_metadata = {'metadata': {u'test': u'cde'}, 'id': u'def'}
        self.assertEqual(pool_handler.get_machine_metadata_from_iaas('http://10.20.1.2'), response_metadata)

    @patch('tsuruclient.machines.Manager.list')
    def test_get_machine_metadata_from_iaas_return_none(self, mock):
        fake_response_iaas = '''[{"Id": "abc", "Address": "10.10.2.1", "CreationParams": {"test": "abc"}},
                                {"Id": "def", "Address": "10.20.1.2", "CreationParams": {"test": "cde"}}]'''
        mock.return_value = json.loads(fake_response_iaas)
        pool_handler = plugin.TsuruPool("foobar")
        self.assertEqual(pool_handler.get_machine_metadata_from_iaas('http://10.10.2.2'), None)

    @patch('tsuruclient.machines.Manager.list')
    def test_get_machine_metadata_from_iaas_return_none_on_key_error(self, mock):
        fake_response_iaas = '[]'
        mock.return_value = json.loads(fake_response_iaas)
        pool_handler = plugin.TsuruPool("foobar")
        self.assertEqual(pool_handler.get_machine_metadata_from_iaas('http://127.0.0.1'), None)

    @patch('tsuruclient.nodes.Manager.create')
    def test_create_new_node(self, mock):
        mock.return_value = {}
        pool_handler = plugin.TsuruPool("foobar")
        pool_handler.get_nodes = Mock()
        pool_handler.get_nodes.side_effect = [['192.168.1.1', 'http://10.1.1.1:2723',
                                               '10.10.10.1'],
                                              ['192.168.1.1', '10.2.3.2', '10.10.10.1',
                                               'http://10.1.1.1:2723']]
        return_new_node = pool_handler.create_new_node("my_template")
        self.assertEqual(return_new_node, '10.2.3.2')

    @patch('tsuruclient.nodes.Manager.create')
    def test_add_node_to_pool(self, mock):
        mock.return_value = {}
        pool_handler = plugin.TsuruPool("foobar")
        extra_params = {'bla': 'ble', 'xxx': 'yyy'}
        pool_handler.add_node_to_pool('127.0.0.1', '4243', 'http',
                                      extra_params)
        extra_params["address"] = "http://127.0.0.1:4243"
        extra_params["pool"] = "foobar"
        extra_params["register"] = "true"
        mock.assert_called_once_with(**extra_params)

    @patch('tsuruclient.nodes.Manager.create')
    def test_add_node_to_pool_with_none_params(self, mock):
        mock.return_value = {}
        pool_handler = plugin.TsuruPool("foobar")
        pool_handler.add_node_to_pool('127.0.0.1', '4243', 'http', None)
        expected_call = {
            "address": "http://127.0.0.1:4243",
            "pool": "foobar",
            "register": "true",
        }
        mock.assert_called_once_with(**expected_call)

    @patch('tsuruclient.templates.Manager.list')
    def test_return_machines_templates(self, mock):
        machines_templates_json = '''
[
    {
        "Name": "template_red",
        "IaaSName": "cloudstack_prod",
        "Data": [
            {
                "Name": "pool",
                "Value": "foobar"
            },
            {
                "Name": "projectid",
                "Value": "222f0798-e472-4216-a8ed-ce1950f419e8"
            },
            {
                "Name": "displayname",
                "Value": "test_a"
            },
            {
                "Name": "networkids",
                "Value": "513ef8b6-bd98-4e6b-89a6-6ca8a859fbb4"
            }
        ]
    },
    {
        "Name": "template_blue",
        "IaaSName": "cloudstack_prod",
        "Data": [
            {
                "Name": "pool",
                "Value": "infra"
            },
            {
                "Name": "projectid",
                "Value": "222f0798-e472-4216-a8ed-ce1950f419e8"
            },
            {
                "Name": "displayname",
                "Value": "test_infra"
            },
            {
                "Name": "networkids",
                "Value": "97d7ad56-62b4-4d43-805a-2aee42619ac6"
            }
        ]
    },
    {
        "Name": "template_yellow",
        "IaaSName": "cloudstack_dev",
        "Data": [
            {
                "Name": "pool",
                "Value": "foobar"
            },
            {
                "Name": "projectid",
                "Value": "222f0798-e472-4216-a8ed-ce1950f419e8"
            },
            {
                "Name": "displayname",
                "Value": "docker_xxx"
            },
            {
                "Name": "networkids",
                "Value": "97d7ad56-62b4-4d43-805a-2aee42619ac6"
            }
        ]
    },
    {
        "Name": "template_green",
        "IaaSName": "cloudstack_dev",
        "Data": [
            {
                "Name": "pool",
                "Value": "xxx_foobar"
            },
            {
                "Name": "projectid",
                "Value": "222f0798-e472-4216-a8ed-ce1950f419e8"
            },
            {
                "Name": "displayname",
                "Value": "docker_xxx"
            },
            {
                "Name": "networkids",
                "Value": "97d7ad56-62b4-4d43-805a-2aee42619ac6"
            }
        ]
    }
]
        '''
        mock.return_value = json.loads(machines_templates_json)
        pool_handler = plugin.TsuruPool("foobar")
        self.assertListEqual(pool_handler.get_machines_templates(),
                             ['template_red', 'template_yellow'])
        mock.side_effect = Exception()
        self.assertRaisesRegexp(Exception, 'Error getting machines templates',
                                pool_handler.get_machines_templates)

    @patch('tsuruclient.nodes.Manager.remove')
    def test_remove_node_from_pool(self, mock):
        mock.return_value = {}
        pool_handler = plugin.TsuruPool("foobar")
        return_remove_node = pool_handler.remove_node_from_pool('http://127.0.0.1:4243')
        self.assertEqual(return_remove_node, True)
        mock.side_effect = Exception("No such node in storage")
        self.assertRaisesRegexp(Exception, 'No such node in storage',
                                pool_handler.remove_node_from_pool,
                                'http://127.0.0.1:4243')

    @patch('tsuruclient.machines.Manager.list')
    @patch('tsuruclient.machines.Manager.delete')
    def test_remove_machine_from_iaas(self, mock_delete, mock_list):
        fake_response_iaas = '''[{"Id": "abc", "Address": "10.10.2.1", "CreationParams": {"test": "abc"}},
                                {"Id": "def", "Address": "10.20.1.2", "CreationParams": {"test": "cde"}}]'''

        mock_list.return_value = json.loads(fake_response_iaas)
        pool_handler = plugin.TsuruPool("foobar")
        mock_delete.return_value = {}
        self.assertEqual(pool_handler.remove_machine_from_iaas("http://10.20.1.2"), True)

    @patch('tsuruclient.machines.Manager.list')
    def test_remove_machine_from_iaas_with_node_machine_not_found_error(self, mock):
        fake_response_iaas = '''[{"Id": "abc", "Address": "10.10.2.1", "CreationParams": {"test": "abc"}},
                                {"Id": "def", "Address": "10.20.1.2", "CreationParams": {"test": "cde"}}]'''

        mock.return_value = json.loads(fake_response_iaas)
        pool_handler = plugin.TsuruPool("foobar")
        self.assertRaisesRegexp(RemoveMachineFromIaaSError, 'machine 10.20.1.20 not found on IaaS',
                                pool_handler.remove_machine_from_iaas, '10.20.1.20')

    @patch("time.sleep")
    @patch("sys.stderr")
    @patch("sys.stdout")
    @patch('tsuruclient.containers.Manager.move')
    def test_move_node_containers_success(self, mock, stdout, stderr, sleep):
        fake_buffer = [{"Message": "Moving 2 units..."},
                       {"Message": "moving unit: abcd1234"},
                       {"Message": "moving unit: xyzabcd234"},
                       {"Message": "Container moved successfully"}]

        mock.return_value = iter(fake_buffer)

        pool_handler = plugin.TsuruPool("foobar")

        stdout_calls = [call('Moving 2 units...\n'),
                        call('moving unit: abcd1234\n'),
                        call('moving unit: xyzabcd234\n'),
                        call('Container moved successfully\n')]

        move_return_value = pool_handler.move_node_containers('http://10.10.1.2:123', 'https://1.2.3.4')
        self.assertEqual(stdout.write.call_args_list, stdout_calls)
        self.assertEqual(move_return_value, True)
        sleep.assert_has_calls([])

    @patch("time.sleep")
    @patch("sys.stderr")
    @patch("sys.stdout")
    @patch('tsuruclient.containers.Manager.move')
    def test_move_node_containers_invalid_host(self, mock, stdout, stderr, sleep):
        pool_handler = plugin.TsuruPool("foobar")
        self.assertRaisesRegexp(MoveNodeContainersError, 'node address .+ are invalids',
                                pool_handler.move_node_containers,
                                'http://10.10.1.2:123', '1.2.3.4:432')

    @patch("time.sleep")
    @patch("sys.stderr")
    @patch("sys.stdout")
    @patch('tsuruclient.containers.Manager.move')
    def test_move_node_containers_empty_return_stream(self, mock, stdout, stderr, sleep):
        fake_buffer = ''
        self.urlopen_mock.return_value = FakeURLopenResponse(fake_buffer, 200)
        with self.assertRaises(MoveNodeContainersError):
            pool_handler = plugin.TsuruPool("foobar")
            pool_handler.move_node_containers('http://10.10.1.2:123', 'https://1.2.3.4')
        sleep.assert_has_calls([])
        stdout.write.assert_has_calls([])
        stderr.write.assert_has_calls([])

    @patch("time.sleep")
    @patch("sys.stderr")
    @patch("sys.stdout")
    @patch('tsuruclient.containers.Manager.move')
    def test_move_node_containers_success_after_errors(self, mock, stdout, stderr, sleep):
        fake_buffer = [[{"Message": "Moving 2 units..."},
                        {"Message": "Error moving unit: abcd1234"},
                        {"Message": """Error moving container: Error moving
                        unit: cannot connect to Docker endpoint"""},
                        {"Message": "Error moving unit: xyzabcd234"}],
                       [{"Message": "Moving 2 units..."},
                        {"Message": "Error moving unit: abcd1234"},
                        {"Message": """Error moving container: Error moving unit:
                        cannot connect to Docker endpoint"""},
                        {"Message": "Error moving unit: xyzabcd234"}],
                       [{"Message": "Moving unit abcd1234"},
                        {"Message": "Moving unit xyzabc234"},
                        {"Message": "Container moved successfully"}]]

        mock.side_effect = [iter(fake_buffer[0]), iter(fake_buffer[1]),
                            iter(fake_buffer[2])]

        pool_handler = plugin.TsuruPool("foobar")
        move_return_value = pool_handler.move_node_containers('http://1.2.3.4:123', 'http://5.6.7.8:234')
        self.assertEqual(move_return_value, True)

        stderr_calls = []
        for message_block in fake_buffer:
            for line in message_block:
                if line is not '' and 'Error' in line['Message']:
                    message = line['Message']
                    stderr_calls.append(call(str(message + '\n')))

        stdout_calls = [call('Moving 2 units...\n'),
                        call('Retrying move containers from http://1.2.3.4:123 to'
                             ' http://5.6.7.8:234. Waiting for 180 seconds...'),
                        call('Moving 2 units...\n'),
                        call('Retrying move containers from http://1.2.3.4:123 to'
                             ' http://5.6.7.8:234. Waiting for 180 seconds...'),
                        call('Moving unit abcd1234\n'),
                        call('Moving unit xyzabc234\n'),
                        call('Container moved successfully\n')]

        self.assertEqual(stdout.write.call_args_list, stdout_calls)
        self.assertEqual(stderr.write.call_args_list, stderr_calls)
        sleep.assert_has_calls([call(180), call(180)])

    @patch("time.sleep")
    @patch("sys.stderr")
    @patch("sys.stdout")
    @patch('tsuruclient.containers.Manager.move')
    def test_move_node_containers_fail(self, mock, stdout, stderr, sleep):
        fake_buffer = [[{"Message": "Moving 2 units..."},
                        {"Message": "Error moving unit: abcd1234"},
                        {"Message": """Error moving container: Error moving
                        unit: cannot connect to Docker endpoint"""},
                        {"Message": "Error moving unit: xyzabcd234"}],
                       [{"Message": "Moving 2 units..."},
                        {"Message": "Error moving unit: abcd1234"},
                        {"Message": """Error moving container: Error moving unit:
                        cannot connect to Docker endpoint"""},
                        {"Message": "Error moving unit: xyzabcd234"}],
                       [{"Message": "Moving unit abcd1234"},
                        {"Message": "Moving unit xyzabc234"},
                        {"Message": "Error moving unit: 0oi99222"}]]

        mock.side_effect = [iter(fake_buffer[0]), iter(fake_buffer[1]),
                            iter(fake_buffer[2])]

        with self.assertRaises(MoveNodeContainersError):
            pool_handler = plugin.TsuruPool("foobar")
            pool_handler.move_node_containers('http://1.2.3.4:123', 'http://5.6.7.8:234', 0, 2)

        stderr_calls = []
        for message_block in fake_buffer:
            for line in message_block:
                if line is not '' and 'Error' in line['Message']:
                    message = line['Message']
                    stderr_calls.append(call(str(message + '\n')))
        stderr_calls.append(call('Error: Max retry reached for moving on 3 attempts.'))

        stdout_calls = [call('Moving 2 units...\n'),
                        call('Retrying move containers from http://1.2.3.4:123 to'
                             ' http://5.6.7.8:234. Waiting for 180 seconds...'),
                        call('Moving 2 units...\n'),
                        call('Retrying move containers from http://1.2.3.4:123 to'
                             ' http://5.6.7.8:234. Waiting for 180 seconds...'),
                        call('Moving unit abcd1234\n'),
                        call('Moving unit xyzabc234\n')]

        self.assertEqual(stdout.write.call_args_list, stdout_calls)
        self.assertEqual(stderr.write.call_args_list, stderr_calls)
        sleep.assert_has_calls([call(180), call(180)])

    @patch("sys.stdout")
    @patch('pool_recycle.plugin.TsuruPool.get_nodes')
    @patch('pool_recycle.plugin.TsuruPool.get_machines_templates')
    def test_pool_recycle_on_dry_mode(self, get_machines_templates, get_nodes, stdout):
        get_machines_templates.return_value = ['templateA', 'templateB', 'templateC']
        get_nodes.return_value = ['http://127.0.0.1:4243', '10.10.2.2',
                                  '10.2.3.2', 'http://2.3.2.1:2123']
        plugin.pool_recycle('foobar', False, True)
        call_stdout_list = [call('Creating new node on pool "foobar" using "templateA" template\n'),
                            call('Removing node "http://127.0.0.1:4243" from pool "foobar"\n'),
                            call('Moving all containers on old node "http://127.0.0.1:4243" to new node\n'),
                            call('\n'),
                            call('Creating new node on pool "foobar" using "templateB" template\n'),
                            call('Removing node "10.10.2.2" from pool "foobar"\n'),
                            call('Moving all containers on old node "10.10.2.2" to new node\n'),
                            call('\n'),
                            call('Creating new node on pool "foobar" using "templateC" template\n'),
                            call('Removing node "10.2.3.2" from pool "foobar"\n'),
                            call('Moving all containers on old node "10.2.3.2" to new node\n'),
                            call('\n'),
                            call('Creating new node on pool "foobar" using "templateA" template\n'),
                            call('Removing node "http://2.3.2.1:2123" from pool "foobar"\n'),
                            call('Moving all containers on old node "http://2.3.2.1:2123" to new node\n'),
                            call('\n')]

        self.assertEqual(stdout.write.call_args_list, call_stdout_list)

    @patch("sys.stdout")
    @patch('pool_recycle.plugin.TsuruPool')
    def test_pool_recycle_success_removing_node_from_iaas(self, tsuru_pool_mock, stdout):
        tsuru_pool_mock.return_value = FakeTsuruPool('foobar')
        plugin.pool_recycle('foobar', True)
        call_stdout_list = [call('Creating new node on pool "foobar" using templateA template\n'),
                            call('Removing node "127.0.0.1" from pool "foobar"\n'),
                            call('Moving all containers from old node "127.0.0.1" to new node "1.2.3.4"\n'),
                            call('Machine 127.0.0.1 removed from IaaS\n'),
                            call('Creating new node on pool "foobar" using templateB template\n'),
                            call('Removing node "10.10.1.1" from pool "foobar"\n'),
                            call('Moving all containers from old node "10.10.1.1" '
                                 'to new node "5.6.7.8"\n'),
                            call('Machine 10.10.1.1 removed from IaaS\n'),
                            call('Creating new node on pool "foobar" using templateA template\n'),
                            call('Removing node "10.1.1.2" from pool "foobar"\n'),
                            call('Moving all containers from old node "10.1.1.2" to new node "9.10.11.12"\n'),
                            call('Machine 10.1.1.2 removed from IaaS\n')]
        stdout.write.assert_has_calls(call_stdout_list)

    @patch('sys.stderr')
    @patch('sys.stdout')
    @patch('pool_recycle.plugin.TsuruPool')
    def test_pool_recycle_error_on_moving_containers(self, tsuru_pool_mock, stdout, stderr):
        tsuru_pool_mock.return_value = FakeTsuruPool('foobar', True)
        with self.assertRaises(MoveNodeContainersError) as move_exception:
            plugin.pool_recycle('foobar')
        call_stdout_list = [call('Creating new node on pool "foobar" using templateA template\n'),
                            call('Removing node "127.0.0.1" from pool "foobar"\n'),
                            call('Moving all containers from old node "127.0.0.1" to new node "1.2.3.4"\n')]
        exception_msg = move_exception.exception.message
        self.assertEqual(stdout.write.mock_calls, call_stdout_list)
        self.assertEqual(exception_msg, 'error moving 127.0.0.1 to 1.2.3.4')

    @patch('sys.stderr')
    @patch('sys.stdout')
    @patch('pool_recycle.plugin.pool_recycle')
    def test_pool_recycle_parser_with_all_options_set(self, pool_recycle, stdout, stderr):
        args = ["-p", "foobar", "-r", "-d", "-m", "100", "-t", "30", "-P", "2222", "-s", "https"]
        plugin.pool_recycle_parser(args)
        pool_recycle.assert_called_once_with('foobar', True, True, 100, 30, '2222', 'https')

    def tearDown(self):
        self.patcher.stop()
