#!/usr/bin/env python
# Copyright 2012 The Swarming Authors. All rights reserved.
# Use of this source code is governed under the Apache License, Version 2.0 that
# can be found in the LICENSE file.

import cStringIO
import hashlib
import json
import logging
import os
import sys
import tempfile
import unittest

ROOT_DIR = unicode(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'third_party'))

from depot_tools import auto_stub
import isolate
from utils import file_path
from utils import tools
# Create shortcuts.
from isolate import KEY_TOUCHED, KEY_TRACKED, KEY_UNTRACKED


ALGO = hashlib.sha1


def _size(*args):
  return os.stat(os.path.join(ROOT_DIR, *args)).st_size


def hash_file(*args):
  return isolate.isolateserver.hash_file(os.path.join(ROOT_DIR, *args), ALGO)


class IsolateBase(auto_stub.TestCase):
  def setUp(self):
    super(IsolateBase, self).setUp()
    self.old_cwd = os.getcwd()
    self.cwd = tempfile.mkdtemp(prefix='isolate_')
    # Everything should work even from another directory.
    os.chdir(self.cwd)

  def tearDown(self):
    try:
      os.chdir(self.old_cwd)
      isolate.run_isolated.rmtree(self.cwd)
    finally:
      super(IsolateBase, self).tearDown()


class IsolateTest(IsolateBase):
  def test_savedstate_load_minimal(self):
    # The file referenced by 'isolate_file' must exist even if its content is
    # not read.
    open(os.path.join(self.cwd, 'fake.isolate'), 'wb').close()
    values = {
      'isolate_file': 'fake.isolate',
    }
    expected = {
      'algo': 'sha-1',
      'child_isolated_files': [],
      'config_variables': {},
      'command': [],
      'extra_variables': {},
      'files': {},
      'isolate_file': 'fake.isolate',
      'path_variables': {},
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    saved_state = isolate.SavedState.load(values, self.cwd)
    self.assertEqual(expected, saved_state.flatten())

  def test_savedstate_load(self):
    # The file referenced by 'isolate_file' must exist even if its content is
    # not read.
    open(os.path.join(self.cwd, 'fake.isolate'), 'wb').close()
    values = {
      'config_variables': {
        'OS': isolate.get_flavor(),
      },
      'extra_variables': {
        'foo': 42,
      },
      'isolate_file': 'fake.isolate',
    }
    expected = {
      'algo': 'sha-1',
      'child_isolated_files': [],
      'command': [],
      'config_variables': {
        'OS': isolate.get_flavor(),
      },
      'extra_variables': {
        'foo': 42,
      },
      'files': {},
      'isolate_file': 'fake.isolate',
      'path_variables': {},
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    saved_state = isolate.SavedState.load(values, self.cwd)
    self.assertEqual(expected, saved_state.flatten())

  def test_unknown_key(self):
    try:
      isolate.verify_variables({'foo': [],})
      self.fail()
    except AssertionError:
      pass

  def test_unknown_var(self):
    try:
      isolate.verify_condition({'variables': {'foo': [],}}, {})
      self.fail()
    except AssertionError:
      pass

  def test_union(self):
    value1 = {
      'a': set(['A']),
      'b': ['B', 'C'],
      'c': 'C',
    }
    value2 = {
      'a': set(['B', 'C']),
      'b': [],
      'd': set(),
    }
    expected = {
      'a': set(['A', 'B', 'C']),
      'b': ['B', 'C'],
      'c': 'C',
      'd': set(),
    }
    self.assertEqual(expected, isolate.union(value1, value2))

  def test_eval_content(self):
    try:
      # Intrinsics are not available.
      isolate.eval_content('map(str, [1, 2])')
      self.fail()
    except NameError:
      pass

  def test_load_isolate_as_config_empty(self):
    self.assertEqual({}, isolate.load_isolate_as_config(
        self.cwd, {}, None).flatten())

  def test_load_isolate_as_config(self):
    value = {
      'conditions': [
        ['OS=="amiga" or OS=="atari" or OS=="coleco" or OS=="dendy"', {
          'variables': {
            KEY_TRACKED: ['a'],
            KEY_UNTRACKED: ['b'],
            KEY_TOUCHED: ['touched'],
          },
        }],
        ['OS=="atari"', {
          'variables': {
            KEY_TRACKED: ['c', 'x'],
            KEY_UNTRACKED: ['d'],
            KEY_TOUCHED: ['touched_a'],
            'command': ['echo', 'Hello World'],
            'read_only': True,
          },
        }],
        ['OS=="amiga" or OS=="coleco" or OS=="dendy"', {
          'variables': {
            KEY_TRACKED: ['e', 'x'],
            KEY_UNTRACKED: ['f'],
            KEY_TOUCHED: ['touched_e'],
            'command': ['echo', 'You should get an Atari'],
          },
        }],
        ['OS=="amiga"', {
          'variables': {
            KEY_TRACKED: ['g'],
            'read_only': False,
          },
        }],
        ['OS=="amiga" or OS=="atari" or OS=="dendy"', {
          'variables': {
            KEY_UNTRACKED: ['h'],
          },
        }],
      ],
    }
    expected = {
      ('amiga',): {
        'command': ['echo', 'You should get an Atari'],
        KEY_TOUCHED: ['touched', 'touched_e'],
        KEY_TRACKED: ['a', 'e', 'g', 'x'],
        KEY_UNTRACKED: ['b', 'f', 'h'],
        'read_only': False,
      },
      ('atari',): {
        'command': ['echo', 'Hello World'],
        KEY_TOUCHED: ['touched', 'touched_a'],
        KEY_TRACKED: ['a', 'c', 'x'],
        KEY_UNTRACKED: ['b', 'd', 'h'],
        'read_only': True,
      },
      ('coleco',): {
        'command': ['echo', 'You should get an Atari'],
        KEY_TOUCHED: ['touched', 'touched_e'],
        KEY_TRACKED: ['a', 'e', 'x'],
        KEY_UNTRACKED: ['b', 'f'],
      },
      ('dendy',): {
        'command': ['echo', 'You should get an Atari'],
        KEY_TOUCHED: ['touched', 'touched_e'],
        KEY_TRACKED: ['a', 'e', 'x'],
        KEY_UNTRACKED: ['b', 'f', 'h'],
      },
    }
    self.assertEqual(
        expected, isolate.load_isolate_as_config(
            self.cwd, value, None).flatten())

  def test_load_isolate_as_config_duplicate_command(self):
    value = {
      'variables': {
        'command': ['rm', '-rf', '/'],
      },
      'conditions': [
        ['OS=="atari"', {
          'variables': {
            'command': ['echo', 'Hello World'],
          },
        }],
      ],
    }
    try:
      isolate.load_isolate_as_config(self.cwd, value, None)
      self.fail()
    except AssertionError:
      pass

  def test_invert_map(self):
    value = {
      ('amiga',): {
        'command': ['echo', 'You should get an Atari'],
        KEY_TOUCHED: ['touched', 'touched_e'],
        KEY_TRACKED: ['a', 'e', 'g', 'x'],
        KEY_UNTRACKED: ['b', 'f', 'h'],
        'read_only': False,
      },
      ('atari',): {
        'command': ['echo', 'Hello World'],
        KEY_TOUCHED: ['touched', 'touched_a'],
        KEY_TRACKED: ['a', 'c', 'x'],
        KEY_UNTRACKED: ['b', 'd', 'h'],
        'read_only': True,
      },
      ('coleco',): {
        'command': ['echo', 'You should get an Atari'],
        KEY_TOUCHED: ['touched', 'touched_e'],
        KEY_TRACKED: ['a', 'e', 'x'],
        KEY_UNTRACKED: ['b', 'f'],
      },
      ('dendy',): {
        'command': ['echo', 'You should get an Atari'],
        KEY_TOUCHED: ['touched', 'touched_e'],
        KEY_TRACKED: ['a', 'e', 'x'],
        KEY_UNTRACKED: ['b', 'f', 'h'],
      },
    }
    amiga, atari, coleco, dendy = (
        set([(os,)]) for os in ('amiga', 'atari', 'coleco', 'dendy'))
    expected_values = {
      'command': {
        ('echo', 'Hello World'): atari,
        ('echo', 'You should get an Atari'): amiga | coleco | dendy,
      },
      KEY_TRACKED: {
        'a': amiga | atari | coleco | dendy,
        'c': atari,
        'e': amiga | coleco | dendy,
        'g': amiga,
        'x': amiga | atari | coleco | dendy,
      },
      KEY_UNTRACKED: {
        'b': amiga | atari | coleco | dendy,
        'd': atari,
        'f': amiga | coleco | dendy,
        'h': amiga | atari | dendy,
      },
      KEY_TOUCHED: {
        'touched': amiga | atari | coleco | dendy,
        'touched_a': atari,
        'touched_e': amiga | coleco | dendy,
      },
      'read_only': {
        False: amiga,
        True: atari,
      },
    }
    actual_values = isolate.invert_map(value)
    self.assertEqual(expected_values, actual_values)

  def test_reduce_inputs(self):
    amiga, atari, coleco, dendy = (
        set([(os,)]) for os in ('amiga', 'atari', 'coleco', 'dendy'))
    values = {
      'command': {
        ('echo', 'Hello World'): atari,
        ('echo', 'You should get an Atari'): amiga | coleco | dendy,
      },
      KEY_TRACKED: {
        'a': amiga | atari | coleco | dendy,
        'c': atari,
        'e': amiga | coleco | dendy,
        'g': amiga,
        'x': amiga | atari | coleco | dendy,
      },
      KEY_UNTRACKED: {
        'b': amiga | atari | coleco | dendy,
        'd': atari,
        'f': amiga | coleco | dendy,
        'h': amiga | atari | dendy,
      },
      KEY_TOUCHED: {
        'touched': amiga | atari | coleco | dendy,
        'touched_a': atari,
        'touched_e': amiga | coleco | dendy,
      },
      'read_only': {
        False: amiga,
        True: atari,
      },
    }
    expected_values = {
      'command': {
        ('echo', 'Hello World'): atari,
        ('echo', 'You should get an Atari'): amiga | coleco | dendy,
      },
      KEY_TRACKED: {
        'a': amiga | atari | coleco | dendy,
        'c': atari,
        'e': amiga | coleco | dendy,
        'g': amiga,
        'x': amiga | atari | coleco | dendy,
      },
      KEY_UNTRACKED: {
        'b': amiga | atari | coleco | dendy,
        'd': atari,
        'f': amiga | coleco | dendy,
        'h': amiga | atari | dendy,
      },
      KEY_TOUCHED: {
        'touched': amiga | atari | coleco | dendy,
        'touched_a': atari,
        'touched_e': amiga | coleco | dendy,
      },
      'read_only': {
        False: amiga,
        True: atari,
      },
    }
    actual_values = isolate.reduce_inputs(values)
    self.assertEqual(expected_values, actual_values)

  def test_reduce_inputs_merge_subfolders_and_files(self):
    linux, mac, win = (set([(os,)]) for os in ('linux', 'mac', 'win'))
    values = {
      KEY_TRACKED: {
        'folder/tracked_file': win,
        'folder_helper/tracked_file': win,
      },
      KEY_UNTRACKED: {
        'folder/': linux | mac | win,
        'folder/subfolder/': win,
        'folder/untracked_file': linux | mac | win,
        'folder_helper/': linux,
      },
      KEY_TOUCHED: {
        'folder/touched_file': win,
        'folder/helper_folder/deep_file': win,
        'folder_helper/touched_file1': mac | win,
        'folder_helper/touched_file2': linux,
      },
    }
    expected_values = {
      'command': {},
      KEY_TRACKED: {
        'folder_helper/tracked_file': win,
      },
      KEY_UNTRACKED: {
        'folder/': linux | mac | win,
        'folder_helper/': linux,
      },
      KEY_TOUCHED: {
        'folder_helper/touched_file1': mac | win,
      },
      'read_only': {},
    }
    actual_values = isolate.reduce_inputs(values)
    self.assertEqual(expected_values, actual_values)

  def test_reduce_inputs_take_strongest_dependency(self):
    amiga, atari, coleco, dendy = (
        set([(os,)]) for os in ('amiga', 'atari', 'coleco', 'dendy'))
    values = {
      'command': {
        ('echo', 'Hello World'): atari,
        ('echo', 'You should get an Atari'): amiga | coleco | dendy,
      },
      KEY_TRACKED: {
        'a': amiga | atari | coleco | dendy,
        'b': amiga | atari | coleco,
      },
      KEY_UNTRACKED: {
        'c': amiga | atari | coleco | dendy,
        'd': amiga | coleco | dendy,
      },
      KEY_TOUCHED: {
        'a': amiga | atari | coleco | dendy,
        'b': atari | coleco | dendy,
        'c': amiga | atari | coleco | dendy,
        'd': atari | coleco | dendy,
      },
    }
    expected_values = {
      'command': {
        ('echo', 'Hello World'): atari,
        ('echo', 'You should get an Atari'): amiga | coleco | dendy,
      },
      KEY_TRACKED: {
        'a': amiga | atari | coleco | dendy,
        'b': amiga | atari | coleco,
      },
      KEY_UNTRACKED: {
        'c': amiga | atari | coleco | dendy,
        'd': amiga | coleco | dendy,
      },
      KEY_TOUCHED: {
        'b': dendy,
        'd': atari,
      },
      'read_only': {},
    }
    actual_values = isolate.reduce_inputs(values)
    self.assertEqual(expected_values, actual_values)

  def test_convert_map_to_isolate_dict(self):
    amiga = ('amiga',)
    atari = ('atari',)
    coleco = ('coleco',)
    dendy = ('dendy',)
    values = {
      'command': {
        ('echo', 'Hello World'): (atari,),
        ('echo', 'You should get an Atari'): (amiga, coleco, dendy),
      },
      KEY_TRACKED: {
        'a': (amiga, atari, coleco, dendy),
        'c': (atari,),
        'e': (amiga, coleco, dendy),
        'g': (amiga,),
        'x': (amiga, atari, coleco, dendy),
      },
      KEY_UNTRACKED: {
        'b': (amiga, atari, coleco, dendy),
        'd': (atari,),
        'f': (amiga, coleco, dendy),
        'h': (amiga, atari, dendy),
      },
      KEY_TOUCHED: {
        'touched': (amiga, atari, coleco, dendy),
        'touched_a': (atari,),
        'touched_e': (amiga, coleco, dendy),
      },
      'read_only': {
        False: (amiga,),
        True: (atari,),
      },
    }
    expected_conditions = [
      ['OS=="amiga"', {
        'variables': {
          KEY_TRACKED: ['g'],
          'read_only': False,
        },
      }],
      ['OS=="amiga" or OS=="atari" or OS=="coleco" or OS=="dendy"', {
        'variables': {
          KEY_TRACKED: ['a', 'x'],
          KEY_UNTRACKED: ['b'],
          KEY_TOUCHED: ['touched'],
        },
      }],
      ['OS=="amiga" or OS=="atari" or OS=="dendy"', {
        'variables': {
          KEY_UNTRACKED: ['h'],
        },
      }],
      ['OS=="amiga" or OS=="coleco" or OS=="dendy"', {
        'variables': {
          'command': ['echo', 'You should get an Atari'],
          KEY_TRACKED: ['e'],
          KEY_UNTRACKED: ['f'],
          KEY_TOUCHED: ['touched_e'],
        },
      }],
      ['OS=="atari"', {
        'variables': {
          'command': ['echo', 'Hello World'],
          KEY_TRACKED: ['c'],
          KEY_UNTRACKED: ['d'],
          KEY_TOUCHED: ['touched_a'],
          'read_only': True,
        },
      }],
    ]
    actual = isolate.convert_map_to_isolate_dict(values, ('OS',))
    self.assertEqual(expected_conditions, sorted(actual.pop('conditions')))
    self.assertFalse(actual)

  def test_merge_two_empty(self):
    # Flat stay flat. Pylint is confused about union() return type.
    # pylint: disable=E1103
    actual = isolate.union(
        isolate.union(
          isolate.Configs(None),
          isolate.load_isolate_as_config(self.cwd, {}, None)),
        isolate.load_isolate_as_config(self.cwd, {}, None)).flatten()
    self.assertEqual({}, actual)

  def test_merge_empty(self):
    actual = isolate.convert_map_to_isolate_dict(
        isolate.reduce_inputs(isolate.invert_map({})), ('dummy1', 'dummy2'))
    self.assertEqual({'conditions': []}, actual)

  def test_load_two_conditions(self):
    linux = {
      'conditions': [
        ['OS=="linux"', {
          'variables': {
            'isolate_dependency_tracked': [
              'file_linux',
              'file_common',
            ],
          },
        }],
      ],
    }
    mac = {
      'conditions': [
        ['OS=="mac"', {
          'variables': {
            'isolate_dependency_tracked': [
              'file_mac',
              'file_common',
            ],
          },
        }],
      ],
    }
    expected = {
      ('linux',): {
        'isolate_dependency_tracked': ['file_common', 'file_linux'],
      },
      ('mac',): {
        'isolate_dependency_tracked': ['file_common', 'file_mac'],
      },
    }
    # Pylint is confused about union() return type.
    # pylint: disable=E1103
    configs = isolate.union(
        isolate.union(
          isolate.Configs(None),
          isolate.load_isolate_as_config(self.cwd, linux, None)),
        isolate.load_isolate_as_config(self.cwd, mac, None)).flatten()
    self.assertEqual(expected, configs)

  def test_load_three_conditions(self):
    linux = {
      'conditions': [
        ['OS=="linux" and chromeos==1', {
          'variables': {
            'isolate_dependency_tracked': [
              'file_linux',
              'file_common',
            ],
          },
        }],
      ],
    }
    mac = {
      'conditions': [
        ['OS=="mac" and chromeos==0', {
          'variables': {
            'isolate_dependency_tracked': [
              'file_mac',
              'file_common',
            ],
          },
        }],
      ],
    }
    win = {
      'conditions': [
        ['OS=="win" and chromeos==0', {
          'variables': {
            'isolate_dependency_tracked': [
              'file_win',
              'file_common',
            ],
          },
        }],
      ],
    }
    expected = {
      ('linux', 1): {
        'isolate_dependency_tracked': ['file_common', 'file_linux'],
      },
      ('mac', 0): {
        'isolate_dependency_tracked': ['file_common', 'file_mac'],
      },
      ('win', 0): {
        'isolate_dependency_tracked': ['file_common', 'file_win'],
      },
    }
    # Pylint is confused about union() return type.
    # pylint: disable=E1103
    configs = isolate.union(
        isolate.union(
          isolate.union(
            isolate.Configs(None),
            isolate.load_isolate_as_config(self.cwd, linux, None)),
          isolate.load_isolate_as_config(self.cwd, mac, None)),
        isolate.load_isolate_as_config(self.cwd, win, None)).flatten()
    self.assertEqual(expected, configs)

  def test_merge_three_conditions(self):
    values = {
      ('linux',): {
        'isolate_dependency_tracked': ['file_common', 'file_linux'],
      },
      ('mac',): {
        'isolate_dependency_tracked': ['file_common', 'file_mac'],
      },
      ('win',): {
        'isolate_dependency_tracked': ['file_common', 'file_win'],
      },
    }
    expected = {
      'conditions': [
        ['OS=="linux"', {
          'variables': {
            'isolate_dependency_tracked': [
              'file_linux',
            ],
          },
        }],
        ['OS=="linux" or OS=="mac" or OS=="win"', {
          'variables': {
            'isolate_dependency_tracked': [
              'file_common',
            ],
          },
        }],
        ['OS=="mac"', {
          'variables': {
            'isolate_dependency_tracked': [
              'file_mac',
            ],
          },
        }],
        ['OS=="win"', {
          'variables': {
            'isolate_dependency_tracked': [
              'file_win',
            ],
          },
        }],
      ],
    }
    actual = isolate.convert_map_to_isolate_dict(
        isolate.reduce_inputs(isolate.invert_map(values)), ('OS',))
    self.assertEqual(expected, actual)

  def test_configs_comment(self):
    # Pylint is confused with isolate.union() return type.
    # pylint: disable=E1103
    configs = isolate.union(
        isolate.load_isolate_as_config(
            self.cwd, {}, '# Yo dawg!\n# Chill out.\n'),
        isolate.load_isolate_as_config(self.cwd, {}, None))
    self.assertEqual('# Yo dawg!\n# Chill out.\n', configs.file_comment)

    configs = isolate.union(
        isolate.load_isolate_as_config(self.cwd, {}, None),
        isolate.load_isolate_as_config(
            self.cwd, {}, '# Yo dawg!\n# Chill out.\n'))
    self.assertEqual('# Yo dawg!\n# Chill out.\n', configs.file_comment)

    # Only keep the first one.
    configs = isolate.union(
        isolate.load_isolate_as_config(self.cwd, {}, '# Yo dawg!\n'),
        isolate.load_isolate_as_config(self.cwd, {}, '# Chill out.\n'))
    self.assertEqual('# Yo dawg!\n', configs.file_comment)

  def test_load_with_includes(self):
    included_isolate = {
      'variables': {
        'isolate_dependency_tracked': [
          'file_common',
        ],
      },
      'conditions': [
        ['OS=="linux"', {
          'variables': {
            'isolate_dependency_tracked': [
              'file_linux',
            ],
          },
        }, {
          'variables': {
            'isolate_dependency_tracked': [
              'file_non_linux',
            ],
          },
        }],
      ],
    }
    tools.write_json(
        os.path.join(self.cwd, 'included.isolate'), included_isolate, True)
    values = {
      'includes': ['included.isolate'],
      'variables': {
        'isolate_dependency_tracked': [
          'file_less_common',
        ],
      },
      'conditions': [
        ['OS=="mac"', {
          'variables': {
            'isolate_dependency_tracked': [
              'file_mac',
            ],
          },
        }],
      ],
    }
    actual = isolate.load_isolate_as_config(self.cwd, values, None)

    expected = {
      ('linux',): {
        'isolate_dependency_tracked': [
          'file_common',
          'file_less_common',
          'file_linux',
        ],
      },
      ('mac',): {
        'isolate_dependency_tracked': [
          'file_common',
          'file_less_common',
          'file_mac',
          'file_non_linux',
        ],
      },
      ('win',): {
        'isolate_dependency_tracked': [
          'file_common',
          'file_less_common',
          'file_non_linux',
        ],
      },
    }
    self.assertEqual(expected, actual.flatten())

  def test_load_with_includes_with_commands(self):
    # This one is messy.
    isolate1 = {
      'conditions': [
        ['OS=="linux"', {
          'variables': {
            'command': [
              'foo', 'bar',
            ],
            'isolate_dependency_tracked': [
              'file_linux',
            ],
          },
        }, {
          'variables': {
            'isolate_dependency_tracked': [
              'file_non_linux',
            ],
          },
        }],
        ['OS=="win"', {
          'variables': {
            'command': [
              'foo', 'bar',
            ],
          },
        }],
      ],
    }
    tools.write_json(os.path.join(self.cwd, 'isolate1.isolate'), isolate1, True)
    isolate2 = {
      'conditions': [
        ['OS=="linux" or OS=="mac"', {
          'variables': {
            'command': [
              'zoo',
            ],
            'isolate_dependency_tracked': [
              'other/file',
            ],
          },
        }],
      ],
    }
    tools.write_json(os.path.join(self.cwd, 'isolate2.isolate'), isolate2, True)
    isolate3 = {
      'includes': ['isolate1.isolate', 'isolate2.isolate'],
      'conditions': [
        ['OS=="mac"', {
          'variables': {
            'command': [
              'yo', 'dawg',
            ],
            'isolate_dependency_tracked': [
              'file_mac',
            ],
          },
        }],
      ],
    }

    actual = isolate.load_isolate_as_config(self.cwd, isolate3, None)
    expected = {
      ('linux',): {
        # Last included takes precedence.
        'command': ['zoo'],
        'isolate_dependency_tracked': ['file_linux', 'other/file'],
      },
      ('mac',): {
        # Command in isolate3 takes precedence.
        'command': ['yo', 'dawg'],
        'isolate_dependency_tracked': [
          'file_mac',
          'file_non_linux',
          'other/file',
        ],
      },
      ('win',): {
        'command': ['foo', 'bar'],
        'isolate_dependency_tracked': ['file_non_linux'],
      },
    }
    self.assertEqual(expected, actual.flatten())

  def test_extract_comment(self):
    self.assertEqual(
        '# Foo\n# Bar\n', isolate.extract_comment('# Foo\n# Bar\n{}'))
    self.assertEqual('', isolate.extract_comment('{}'))

  def _test_pretty_print_impl(self, value, expected):
    actual = cStringIO.StringIO()
    isolate.pretty_print(value, actual)
    self.assertEqual(expected, actual.getvalue())

  def test_pretty_print_empty(self):
    self._test_pretty_print_impl({}, '{\n}\n')

  def test_pretty_print_mid_size(self):
    value = {
      'variables': {
        'bar': [
          'file1',
          'file2',
        ],
      },
      'conditions': [
        ['OS=\"foo\"', {
          'variables': {
            isolate.KEY_UNTRACKED: [
              'dir1',
              'dir2',
            ],
            isolate.KEY_TRACKED: [
              'file4',
              'file3',
            ],
            'command': ['python', '-c', 'print "H\\i\'"'],
            'read_only': True,
            'relative_cwd': 'isol\'at\\e',
          },
        }],
        ['OS=\"bar\"', {
          'variables': {},
        }, {
          'variables': {},
        }],
      ],
    }
    expected = (
        "{\n"
        "  'variables': {\n"
        "    'bar': [\n"
        "      'file1',\n"
        "      'file2',\n"
        "    ],\n"
        "  },\n"
        "  'conditions': [\n"
        "    ['OS=\"foo\"', {\n"
        "      'variables': {\n"
        "        'command': [\n"
        "          'python',\n"
        "          '-c',\n"
        "          'print \"H\\i\'\"',\n"
        "        ],\n"
        "        'relative_cwd': 'isol\\'at\\\\e',\n"
        "        'read_only': True\n"
        "        'isolate_dependency_tracked': [\n"
        "          'file4',\n"
        "          'file3',\n"
        "        ],\n"
        "        'isolate_dependency_untracked': [\n"
        "          'dir1',\n"
        "          'dir2',\n"
        "        ],\n"
        "      },\n"
        "    }],\n"
        "    ['OS=\"bar\"', {\n"
        "      'variables': {\n"
        "      },\n"
        "    }, {\n"
        "      'variables': {\n"
        "      },\n"
        "    }],\n"
        "  ],\n"
        "}\n")
    self._test_pretty_print_impl(value, expected)

  def test_convert_old_to_new_bypass(self):
    isolate_not_needing_conversion = {
      'conditions': [
        ['OS=="mac"', {'variables': {'foo': 'bar'}}],
        ['condition shouldn\'t matter', {'variables': {'x': 'y'}}],
      ],
    }
    self.assertEqual(
        isolate_not_needing_conversion,
        isolate.convert_old_to_new_format(isolate_not_needing_conversion))

  def test_convert_old_to_new_else(self):
    isolate_with_else_clauses = {
      'conditions': [
        ['OS=="mac"', {
          'variables': {'foo': 'bar'},
        }, {
          'variables': {'x': 'y'},
        }],
        ['OS=="foo"', {
        }, {
          'variables': {'p': 'q'},
        }],
      ],
    }
    expected_output = {
      'conditions': [
        ['OS=="foo" or OS=="linux" or OS=="win"', {
          'variables': {'x': 'y'},
        }],
        ['OS=="linux" or OS=="mac" or OS=="win"', {
          'variables': {'p': 'q'},
        }],
        ['OS=="mac"', {
          'variables': {'foo': 'bar'},
        }],
      ],
    }
    self.assertEqual(
        expected_output,
        isolate.convert_old_to_new_format(isolate_with_else_clauses))

  def test_convert_old_to_new_default_variables(self):
    isolate_with_default_variables = {
      'conditions': [
        ['OS=="abc"', {
          'variables': {'foo': 'bar'},
        }],
      ],
      'variables': {'p': 'q'},
    }
    expected_output = {
      'conditions': [
        ['OS=="abc"', {
          'variables': {'foo': 'bar'},
        }],
        ['OS=="abc" or OS=="linux" or OS=="mac" or OS=="win"', {
          'variables': {'p': 'q'},
        }],
      ],
    }
    self.assertEqual(
        expected_output,
        isolate.convert_old_to_new_format(isolate_with_default_variables))

  def test_variable_arg(self):
    parser = isolate.OptionParserIsolate()
    parser.require_isolated = False
    expected_path = {
      'Baz': 'sub=string',
    }
    expected_config = {
      'Foo': 'bar',
      'OS': isolate.get_flavor(),
    }
    expected_extra = {
      'biz': 'b uz=a',
      'EXECUTABLE_SUFFIX': '.exe' if isolate.get_flavor() == 'win' else '',
    }

    options, args = parser.parse_args(
        ['--config-variable', 'Foo', 'bar',
          '--path-variable', 'Baz=sub=string',
          '--extra-variable', 'biz', 'b uz=a'])
    self.assertEqual(expected_path, options.path_variables)
    self.assertEqual(expected_config, options.config_variables)
    self.assertEqual(expected_extra, options.extra_variables)
    self.assertEqual([], args)

  def test_variable_arg_fail(self):
    parser = isolate.OptionParserIsolate()
    self.mock(sys, 'stderr', cStringIO.StringIO())
    with self.assertRaises(SystemExit):
      parser.parse_args(['--config-variable', 'Foo'])

  def test_blacklist(self):
    ok = [
      '.git2',
      '.pyc',
      '.swp',
      'allo.git',
      'foo',
    ]
    blocked = [
      '.git',
      os.path.join('foo', '.git'),
      'foo.pyc',
      'bar.swp',
    ]
    blacklist = tools.gen_blacklist(isolate.isolateserver.DEFAULT_BLACKLIST)
    for i in ok:
      self.assertFalse(blacklist(i), i)
    for i in blocked:
      self.assertTrue(blacklist(i), i)

  def test_blacklist_chromium(self):
    ok = [
      '.run_test_cases',
      'testserver.log2',
    ]
    blocked = [
      'foo.run_test_cases',
      'testserver.log',
      os.path.join('foo', 'testserver.log'),
    ]
    blacklist = tools.gen_blacklist(isolate.isolateserver.DEFAULT_BLACKLIST)
    for i in ok:
      self.assertFalse(blacklist(i), i)
    for i in blocked:
      self.assertTrue(blacklist(i), i)


class IsolateLoad(IsolateBase):
  def setUp(self):
    super(IsolateLoad, self).setUp()
    self.directory = tempfile.mkdtemp(prefix='isolate_')

  def tearDown(self):
    try:
      isolate.run_isolated.rmtree(self.directory)
    finally:
      super(IsolateLoad, self).tearDown()

  def _get_option(self, isolate_file):
    OS = isolate.get_flavor()
    chromeos_value = int(OS == 'linux')
    class Options(object):
      isolated = os.path.join(self.directory, 'foo.isolated')
      outdir = os.path.join(self.directory, 'outdir')
      isolate = isolate_file
      path_variables = {}
      config_variables = {'OS': OS, 'chromeos': chromeos_value}
      extra_variables = {'foo': 'bar'}
      ignore_broken_items = False
    return Options()

  def _cleanup_isolated(self, expected_isolated):
    """Modifies isolated to remove the non-deterministic parts."""
    if sys.platform == 'win32':
      # 'm' are not saved in windows.
      for values in expected_isolated['files'].itervalues():
        self.assertTrue(values.pop('m'))

  def _cleanup_saved_state(self, actual_saved_state):
    for item in actual_saved_state['files'].itervalues():
      self.assertTrue(item.pop('t'))

  def test_load_stale_isolated(self):
    isolate_file = os.path.join(
        ROOT_DIR, 'tests', 'isolate', 'touch_root.isolate')

    # Data to be loaded in the .isolated file. Do not create a .state file.
    input_data = {
      'command': ['python'],
      'files': {
        'foo': {
          "m": 416,
          "h": "invalid",
          "s": 538,
          "t": 1335146921,
        },
        os.path.join('tests', 'isolate', 'touch_root.py'): {
          "m": 488,
          "h": "invalid",
          "s": 538,
          "t": 1335146921,
        },
      },
    }
    options = self._get_option(isolate_file)
    tools.write_json(options.isolated, input_data, False)

    # A CompleteState object contains two parts:
    # - Result instance stored in complete_state.isolated, corresponding to the
    #   .isolated file, is what is read by run_test_from_archive.py.
    # - SavedState instance stored in compelte_state.saved_state,
    #   corresponding to the .state file, which is simply to aid the developer
    #   when re-running the same command multiple times and contain
    #   discardable information.
    complete_state = isolate.load_complete_state(options, self.cwd, None, False)
    actual_isolated = complete_state.saved_state.to_isolated()
    actual_saved_state = complete_state.saved_state.flatten()

    expected_isolated = {
      'algo': 'sha-1',
      'command': ['python', 'touch_root.py'],
      'files': {
        os.path.join(u'tests', 'isolate', 'touch_root.py'): {
          'm': 488,
          'h': hash_file('tests', 'isolate', 'touch_root.py'),
          's': _size('tests', 'isolate', 'touch_root.py'),
        },
        u'isolate.py': {
          'm': 488,
          'h': hash_file('isolate.py'),
          's': _size('isolate.py'),
        },
      },
      'os': isolate.get_flavor(),
      'relative_cwd': os.path.join(u'tests', 'isolate'),
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    self._cleanup_isolated(expected_isolated)
    self.assertEqual(expected_isolated, actual_isolated)

    expected_saved_state = {
      'algo': 'sha-1',
      'child_isolated_files': [],
      'command': ['python', 'touch_root.py'],
      'config_variables': {
        'OS': isolate.get_flavor(),
        'chromeos': options.config_variables['chromeos'],
      },
      'extra_variables': {
        'foo': 'bar',
      },
      'files': {
        os.path.join(u'tests', 'isolate', 'touch_root.py'): {
          'm': 488,
          'h': hash_file('tests', 'isolate', 'touch_root.py'),
          's': _size('tests', 'isolate', 'touch_root.py'),
        },
        u'isolate.py': {
          'm': 488,
          'h': hash_file('isolate.py'),
          's': _size('isolate.py'),
        },
      },
      'isolate_file': file_path.safe_relpath(
          file_path.get_native_path_case(isolate_file),
          os.path.dirname(options.isolated)),
      'relative_cwd': os.path.join(u'tests', 'isolate'),
      'path_variables': {},
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    self._cleanup_isolated(expected_saved_state)
    self._cleanup_saved_state(actual_saved_state)
    self.assertEqual(expected_saved_state, actual_saved_state)

  def test_subdir(self):
    # The resulting .isolated file will be missing ../../isolate.py. It is
    # because this file is outside the --subdir parameter.
    isolate_file = os.path.join(
        ROOT_DIR, 'tests', 'isolate', 'touch_root.isolate')
    options = self._get_option(isolate_file)
    chromeos_value = int(isolate.get_flavor() == 'linux')
    options.config_variables['chromeos'] = chromeos_value
    complete_state = isolate.load_complete_state(
        options, self.cwd, os.path.join('tests', 'isolate'), False)
    actual_isolated = complete_state.saved_state.to_isolated()
    actual_saved_state = complete_state.saved_state.flatten()

    expected_isolated =  {
      'algo': 'sha-1',
      'command': ['python', 'touch_root.py'],
      'files': {
        os.path.join(u'tests', 'isolate', 'touch_root.py'): {
          'm': 488,
          'h': hash_file('tests', 'isolate', 'touch_root.py'),
          's': _size('tests', 'isolate', 'touch_root.py'),
        },
      },
      'os': isolate.get_flavor(),
      'relative_cwd': os.path.join(u'tests', 'isolate'),
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    self._cleanup_isolated(expected_isolated)
    self.assertEqual(expected_isolated, actual_isolated)

    expected_saved_state = {
      'algo': 'sha-1',
      'child_isolated_files': [],
      'command': ['python', 'touch_root.py'],
      'config_variables': {
        'OS': isolate.get_flavor(),
        'chromeos': chromeos_value,
      },
      'extra_variables': {
        'foo': 'bar',
      },
      'files': {
        os.path.join(u'tests', 'isolate', 'touch_root.py'): {
          'm': 488,
          'h': hash_file('tests', 'isolate', 'touch_root.py'),
          's': _size('tests', 'isolate', 'touch_root.py'),
        },
      },
      'isolate_file': file_path.safe_relpath(
          file_path.get_native_path_case(isolate_file),
          os.path.dirname(options.isolated)),
      'relative_cwd': os.path.join(u'tests', 'isolate'),
      'path_variables': {},
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    self._cleanup_isolated(expected_saved_state)
    self._cleanup_saved_state(actual_saved_state)
    self.assertEqual(expected_saved_state, actual_saved_state)

  def test_subdir_variable(self):
    # the resulting .isolated file will be missing ../../isolate.py. it is
    # because this file is outside the --subdir parameter.
    isolate_file = os.path.join(
        ROOT_DIR, 'tests', 'isolate', 'touch_root.isolate')
    options = self._get_option(isolate_file)
    chromeos_value = int(isolate.get_flavor() == 'linux')
    options.config_variables['chromeos'] = chromeos_value
    # Path variables are keyed on the directory containing the .isolate file.
    options.path_variables['TEST_ISOLATE'] = '.'
    # Note that options.isolated is in self.directory, which is a temporary
    # directory.
    complete_state = isolate.load_complete_state(
        options, os.path.join(ROOT_DIR, 'tests', 'isolate'),
        '<(TEST_ISOLATE)', False)
    actual_isolated = complete_state.saved_state.to_isolated()
    actual_saved_state = complete_state.saved_state.flatten()

    expected_isolated =  {
      'algo': 'sha-1',
      'command': ['python', 'touch_root.py'],
      'files': {
        os.path.join('tests', 'isolate', 'touch_root.py'): {
          'm': 488,
          'h': hash_file('tests', 'isolate', 'touch_root.py'),
          's': _size('tests', 'isolate', 'touch_root.py'),
        },
      },
      'os': isolate.get_flavor(),
      'relative_cwd': os.path.join(u'tests', 'isolate'),
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    self._cleanup_isolated(expected_isolated)
    self.assertEqual(expected_isolated, actual_isolated)

    # It is important to note:
    # - the root directory is ROOT_DIR.
    # - relative_cwd is tests/isolate.
    # - TEST_ISOLATE is based of relative_cwd, so it represents tests/isolate.
    # - anything outside TEST_ISOLATE was not included in the 'files' section.
    expected_saved_state = {
      'algo': 'sha-1',
      'child_isolated_files': [],
      'command': ['python', 'touch_root.py'],
      'config_variables': {
        'OS': isolate.get_flavor(),
        'chromeos': chromeos_value,
      },
      'extra_variables': {
        'foo': 'bar',
      },
      'files': {
        os.path.join(u'tests', 'isolate', 'touch_root.py'): {
          'm': 488,
          'h': hash_file('tests', 'isolate', 'touch_root.py'),
          's': _size('tests', 'isolate', 'touch_root.py'),
        },
      },
      'isolate_file': file_path.safe_relpath(
          file_path.get_native_path_case(isolate_file),
          os.path.dirname(options.isolated)),
      'relative_cwd': os.path.join(u'tests', 'isolate'),
      'path_variables': {
        'TEST_ISOLATE': '.',
      },
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    self._cleanup_isolated(expected_saved_state)
    self._cleanup_saved_state(actual_saved_state)
    self.assertEqual(expected_saved_state, actual_saved_state)

  def test_variable_not_exist(self):
    isolate_file = os.path.join(
        ROOT_DIR, 'tests', 'isolate', 'touch_root.isolate')
    options = self._get_option(isolate_file)
    options.path_variables['PRODUCT_DIR'] = os.path.join(u'tests', u'isolate')
    native_cwd = file_path.get_native_path_case(unicode(self.cwd))
    try:
      isolate.load_complete_state(options, self.cwd, None, False)
      self.fail()
    except isolate.ExecutionError, e:
      self.assertEqual(
          'PRODUCT_DIR=%s is not a directory' %
            os.path.join(native_cwd, 'tests', 'isolate'),
          e.args[0])

  def test_variable(self):
    isolate_file = os.path.join(
        ROOT_DIR, 'tests', 'isolate', 'touch_root.isolate')
    options = self._get_option(isolate_file)
    chromeos_value = int(isolate.get_flavor() == 'linux')
    options.config_variables['chromeos'] = chromeos_value
    options.path_variables['PRODUCT_DIR'] = os.path.join('tests', 'isolate')
    complete_state = isolate.load_complete_state(options, ROOT_DIR, None, False)
    actual_isolated = complete_state.saved_state.to_isolated()
    actual_saved_state = complete_state.saved_state.flatten()

    expected_isolated =  {
      'algo': 'sha-1',
      'command': ['python', 'touch_root.py'],
      'files': {
        u'isolate.py': {
          'm': 488,
          'h': hash_file('isolate.py'),
          's': _size('isolate.py'),
        },
        os.path.join(u'tests', 'isolate', 'touch_root.py'): {
          'm': 488,
          'h': hash_file('tests', 'isolate', 'touch_root.py'),
          's': _size('tests', 'isolate', 'touch_root.py'),
        },
      },
      'os': isolate.get_flavor(),
      'relative_cwd': os.path.join(u'tests', 'isolate'),
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    self._cleanup_isolated(expected_isolated)
    self.assertEqual(expected_isolated, actual_isolated)

    expected_saved_state = {
      'algo': 'sha-1',
      'child_isolated_files': [],
      'command': ['python', 'touch_root.py'],
      'config_variables': {
        'OS': isolate.get_flavor(),
        'chromeos': chromeos_value,
      },
      'extra_variables': {
        'foo': 'bar',
      },
      'files': {
        u'isolate.py': {
          'm': 488,
          'h': hash_file('isolate.py'),
          's': _size('isolate.py'),
        },
        os.path.join(u'tests', 'isolate', 'touch_root.py'): {
          'm': 488,
          'h': hash_file('tests', 'isolate', 'touch_root.py'),
          's': _size('tests', 'isolate', 'touch_root.py'),
        },
      },
      'isolate_file': file_path.safe_relpath(
          file_path.get_native_path_case(isolate_file),
          os.path.dirname(options.isolated)),
      'relative_cwd': os.path.join(u'tests', 'isolate'),
      'path_variables': {
        'PRODUCT_DIR': '.',
      },
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    self._cleanup_isolated(expected_saved_state)
    self._cleanup_saved_state(actual_saved_state)
    self.assertEqual(expected_saved_state, actual_saved_state)
    self.assertEqual([], os.listdir(self.directory))

  def test_root_dir_because_of_variable(self):
    # Ensures that load_isolate() works even when path variables have deep root
    # dirs. The end result is similar to touch_root.isolate, except that
    # no_run.isolate doesn't reference '..' at all.
    #
    # A real world example would be PRODUCT_DIR=../../out/Release but nothing in
    # this directory is mapped.
    #
    # Imagine base/base_unittests.isolate would not map anything in
    # PRODUCT_DIR. In that case, the automatically determined root dir is
    # src/base, since nothing outside this directory is mapped.
    isolate_file = os.path.join(
        ROOT_DIR, 'tests', 'isolate', 'no_run.isolate')
    options = self._get_option(isolate_file)
    chromeos_value = int(isolate.get_flavor() == 'linux')
    # Any directory outside ROOT_DIR/tests/isolate.
    options.path_variables['PRODUCT_DIR'] = os.path.join('third_party')
    complete_state = isolate.load_complete_state(options, ROOT_DIR, None, False)
    actual_isolated = complete_state.saved_state.to_isolated()
    actual_saved_state = complete_state.saved_state.flatten()

    expected_isolated = {
      'algo': 'sha-1',
      'files': {
        os.path.join(u'tests', 'isolate', 'files1', 'subdir', '42.txt'): {
          'm': 416,
          'h': hash_file('tests', 'isolate', 'files1', 'subdir', '42.txt'),
          's': _size('tests', 'isolate', 'files1', 'subdir', '42.txt'),
        },
        os.path.join(u'tests', 'isolate', 'files1', 'test_file1.txt'): {
          'm': 416,
          'h': hash_file('tests', 'isolate', 'files1', 'test_file1.txt'),
          's': _size('tests', 'isolate', 'files1', 'test_file1.txt'),
        },
        os.path.join(u'tests', 'isolate', 'files1', 'test_file2.txt'): {
          'm': 416,
          'h': hash_file('tests', 'isolate', 'files1', 'test_file2.txt'),
          's': _size('tests', 'isolate', 'files1', 'test_file2.txt'),
        },
        os.path.join(u'tests', 'isolate', 'no_run.isolate'): {
          'm': 416,
          'h': hash_file('tests', 'isolate', 'no_run.isolate'),
          's': _size('tests', 'isolate', 'no_run.isolate'),
        },
      },
      'os': isolate.get_flavor(),
      'relative_cwd': os.path.join(u'tests', 'isolate'),
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    self._cleanup_isolated(expected_isolated)
    self.assertEqual(expected_isolated, actual_isolated)

    expected_saved_state = {
      'algo': 'sha-1',
      'child_isolated_files': [],
      'command': [],
      'config_variables': {
        'OS': isolate.get_flavor(),
        'chromeos': chromeos_value,
      },
      'extra_variables': {
        'foo': 'bar',
      },
      'files': {
        os.path.join(u'tests', 'isolate', 'files1', 'subdir', '42.txt'): {
          'm': 416,
          'h': hash_file('tests', 'isolate', 'files1', 'subdir', '42.txt'),
          's': _size('tests', 'isolate', 'files1', 'subdir', '42.txt'),
        },
        os.path.join(u'tests', 'isolate', 'files1', 'test_file1.txt'): {
          'm': 416,
          'h': hash_file('tests', 'isolate', 'files1', 'test_file1.txt'),
          's': _size('tests', 'isolate', 'files1', 'test_file1.txt'),
        },
        os.path.join(u'tests', 'isolate', 'files1', 'test_file2.txt'): {
          'm': 416,
          'h': hash_file('tests', 'isolate', 'files1', 'test_file2.txt'),
          's': _size('tests', 'isolate', 'files1', 'test_file2.txt'),
        },
        os.path.join(u'tests', 'isolate', 'no_run.isolate'): {
          'm': 416,
          'h': hash_file('tests', 'isolate', 'no_run.isolate'),
          's': _size('tests', 'isolate', 'no_run.isolate'),
        },
      },
      'isolate_file': file_path.safe_relpath(
          file_path.get_native_path_case(isolate_file),
          os.path.dirname(options.isolated)),
      'relative_cwd': os.path.join(u'tests', 'isolate'),
      'path_variables': {
        'PRODUCT_DIR': os.path.join(u'..', '..', 'third_party'),
      },
      'version': isolate.isolateserver.ISOLATED_FILE_VERSION,
    }
    self._cleanup_isolated(expected_saved_state)
    self._cleanup_saved_state(actual_saved_state)
    self.assertEqual(expected_saved_state, actual_saved_state)
    self.assertEqual([], os.listdir(self.directory))

  def test_chromium_split(self):
    # Create an .isolate file and a tree of random stuff.
    isolate_file = os.path.join(
        ROOT_DIR, 'tests', 'isolate', 'split.isolate')
    options = self._get_option(isolate_file)
    options.path_variables = {
      'DEPTH': '.',
      'PRODUCT_DIR': os.path.join('files1'),
    }
    options.config_variables = {
      'OS': isolate.get_flavor(),
    }
    complete_state = isolate.load_complete_state(
        options, os.path.join(ROOT_DIR, 'tests', 'isolate'), None, False)
    # By saving the files, it forces splitting the data up.
    complete_state.save_files()

    actual_isolated_master = tools.read_json(
        os.path.join(self.directory, 'foo.isolated'))
    expected_isolated_master = {
      u'algo': u'sha-1',
      u'command': [u'python', u'split.py'],
      u'files': {
        u'split.py': {
          u'm': 488,
          u'h': unicode(hash_file('tests', 'isolate', 'split.py')),
          u's': _size('tests', 'isolate', 'split.py'),
        },
      },
      u'includes': [
        unicode(hash_file(os.path.join(self.directory, 'foo.0.isolated'))),
        unicode(hash_file(os.path.join(self.directory, 'foo.1.isolated'))),
      ],
      u'os': unicode(isolate.get_flavor()),
      u'relative_cwd': u'.',
      u'version': unicode(isolate.isolateserver.ISOLATED_FILE_VERSION),
    }
    self._cleanup_isolated(expected_isolated_master)
    self.assertEqual(expected_isolated_master, actual_isolated_master)

    actual_isolated_0 = tools.read_json(
        os.path.join(self.directory, 'foo.0.isolated'))
    expected_isolated_0 = {
      u'algo': u'sha-1',
      u'files': {
        os.path.join(u'test', 'data', 'foo.txt'): {
          u'm': 416,
          u'h': unicode(
              hash_file('tests', 'isolate', 'test', 'data', 'foo.txt')),
          u's': _size('tests', 'isolate', 'test', 'data', 'foo.txt'),
        },
      },
      u'os': unicode(isolate.get_flavor()),
      u'version': unicode(isolate.isolateserver.ISOLATED_FILE_VERSION),
    }
    self._cleanup_isolated(expected_isolated_0)
    self.assertEqual(expected_isolated_0, actual_isolated_0)

    actual_isolated_1 = tools.read_json(
        os.path.join(self.directory, 'foo.1.isolated'))
    expected_isolated_1 = {
      u'algo': u'sha-1',
      u'files': {
        os.path.join(u'files1', 'subdir', '42.txt'): {
          u'm': 416,
          u'h': unicode(
              hash_file('tests', 'isolate', 'files1', 'subdir', '42.txt')),
          u's': _size('tests', 'isolate', 'files1', 'subdir', '42.txt'),
        },
      },
      u'os': unicode(isolate.get_flavor()),
      u'version': unicode(isolate.isolateserver.ISOLATED_FILE_VERSION),
    }
    self._cleanup_isolated(expected_isolated_1)
    self.assertEqual(expected_isolated_1, actual_isolated_1)

    actual_saved_state = tools.read_json(
        isolate.isolatedfile_to_state(options.isolated))
    isolated_base = unicode(os.path.basename(options.isolated))
    expected_saved_state = {
      u'algo': u'sha-1',
      u'child_isolated_files': [
        isolated_base[:-len('.isolated')] + '.0.isolated',
        isolated_base[:-len('.isolated')] + '.1.isolated',
      ],
      u'command': [u'python', u'split.py'],
      u'config_variables': {
        u'OS': unicode(isolate.get_flavor()),
      },
      u'extra_variables': {
        u'foo': u'bar',
      },
      u'files': {
        os.path.join(u'files1', 'subdir', '42.txt'): {
          u'm': 416,
          u'h': unicode(
              hash_file('tests', 'isolate', 'files1', 'subdir', '42.txt')),
          u's': _size('tests', 'isolate', 'files1', 'subdir', '42.txt'),
        },
        u'split.py': {
          u'm': 488,
          u'h': unicode(hash_file('tests', 'isolate', 'split.py')),
          u's': _size('tests', 'isolate', 'split.py'),
        },
        os.path.join(u'test', 'data', 'foo.txt'): {
          u'm': 416,
          u'h': unicode(
              hash_file('tests', 'isolate', 'test', 'data', 'foo.txt')),
          u's': _size('tests', 'isolate', 'test', 'data', 'foo.txt'),
        },
      },
      u'isolate_file': file_path.safe_relpath(
          file_path.get_native_path_case(isolate_file),
          unicode(os.path.dirname(options.isolated))),
      u'relative_cwd': u'.',
      u'path_variables': {
        u'DEPTH': u'.',
        u'PRODUCT_DIR': u'files1',
      },
      u'version': unicode(isolate.isolateserver.ISOLATED_FILE_VERSION),
    }
    self._cleanup_isolated(expected_saved_state)
    self._cleanup_saved_state(actual_saved_state)
    self.assertEqual(expected_saved_state, actual_saved_state)
    self.assertEqual(
        [
          'foo.0.isolated', 'foo.1.isolated',
          'foo.isolated', 'foo.isolated.state',
        ],
        sorted(os.listdir(self.directory)))


class IsolateCommand(IsolateBase):
  def load_complete_state(self, *_):
    """Creates a minimalist CompleteState instance without an .isolated
    reference.
    """
    out = isolate.CompleteState(None, isolate.SavedState(self.cwd))
    out.saved_state.isolate_file = u'blah.isolate'
    out.saved_state.relative_cwd = u''
    return out

  def test_CMDcheck_empty(self):
    isolate_file = os.path.join(self.cwd, 'x.isolate')
    isolated_file = os.path.join(self.cwd, 'x.isolated')
    with open(isolate_file, 'wb') as f:
      f.write('# Foo\n{\n}')

    self.mock(sys, 'stdout', cStringIO.StringIO())
    cmd = ['-i', isolate_file, '-s', isolated_file]
    with self.assertRaises(isolate.isolateserver.ConfigError):
      isolate.CMDcheck(isolate.OptionParserIsolate(), cmd)

  def test_CMDcheck_stale_version(self):
    isolate_file = os.path.join(self.cwd, 'x.isolate')
    isolated_file = os.path.join(self.cwd, 'x.isolated')
    with open(isolate_file, 'wb') as f:
      f.write(
          '# Foo\n'
          '{'
          '  \'conditions\':['
          '    [\'OS=="dendy"\', {'
          '      \'variables\': {'
          '        \'command\': [\'foo\'],'
          '      },'
          '    }],'
          '  ],'
          '}')

    self.mock(sys, 'stdout', cStringIO.StringIO())
    cmd = [
        '-i', isolate_file,
        '-s', isolated_file,
        '--config-variable', 'OS=dendy',
    ]
    self.assertEqual(0, isolate.CMDcheck(isolate.OptionParserIsolate(), cmd))

    with open(isolate_file, 'rb') as f:
      actual = f.read()
    expected = (
        '# Foo\n{  \'conditions\':[    [\'OS=="dendy"\', {      '
        '\'variables\': {        \'command\': [\'foo\'],      },    }],  ],}')
    self.assertEqual(expected, actual)

    with open(isolated_file, 'rb') as f:
      actual_isolated = f.read()
    expected_isolated = (
        '{"algo":"sha-1","command":["foo"],"files":{},"os":"dendy",'
        '"relative_cwd":".","version":"1.2"}')
    self.assertEqual(expected_isolated, actual_isolated)
    isolated_data = json.loads(actual_isolated)

    with open(isolated_file + '.state', 'rb') as f:
      actual_isolated_state = f.read()
    expected_isolated_state = (
        '{"algo":"sha-1","child_isolated_files":[],"command":["foo"],'
        '"config_variables":{"OS":"dendy"},'
        '"extra_variables":{"EXECUTABLE_SUFFIX":""},"files":{},'
        '"isolate_file":"x.isolate","path_variables":{},'
        '"relative_cwd":".","version":"1.2"}')
    self.assertEqual(expected_isolated_state, actual_isolated_state)
    isolated_state_data = json.loads(actual_isolated_state)

    # Now edit the .isolated.state file to break the version number and make
    # sure it doesn't crash.
    with open(isolated_file + '.state', 'wb') as f:
      isolated_state_data['version'] = '100.42'
      json.dump(isolated_state_data, f)
    self.assertEqual(0, isolate.CMDcheck(isolate.OptionParserIsolate(), cmd))

    # Now edit the .isolated file to break the version number and make
    # sure it doesn't crash.
    with open(isolated_file, 'wb') as f:
      isolated_data['version'] = '100.42'
      json.dump(isolated_data, f)
    self.assertEqual(0, isolate.CMDcheck(isolate.OptionParserIsolate(), cmd))

    # Make sure the files were regenerated.
    with open(isolated_file, 'rb') as f:
      actual_isolated = f.read()
    self.assertEqual(expected_isolated, actual_isolated)
    with open(isolated_file + '.state', 'rb') as f:
      actual_isolated_state = f.read()
    self.assertEqual(expected_isolated_state, actual_isolated_state)


  def test_CMDrewrite(self):
    isolate_file = os.path.join(self.cwd, 'x.isolate')
    data = (
      '# Foo',
      '{',
      '}',
    )
    with open(isolate_file, 'wb') as f:
      f.write('\n'.join(data))

    self.mock(sys, 'stdout', cStringIO.StringIO())
    cmd = ['-i', isolate_file]
    self.assertEqual(0, isolate.CMDrewrite(isolate.OptionParserIsolate(), cmd))
    with open(isolate_file, 'rb') as f:
      actual = f.read()

    expected = "# Foo\n{\n  'conditions': [\n  ],\n}\n"
    self.assertEqual(expected, actual)

  if sys.platform != 'win32':
    def test_CMDcheck_no_mode_on_windows(self):
      # Store for Windows, make sure file mode are not included. Hopefully, run
      # this test on another OS.
      isolate_file = os.path.join(
          ROOT_DIR, 'tests', 'isolate', 'symlink_full.isolate')
      isolated_file = os.path.join(self.cwd, 'foo.isolated')
      cmd = [
        '-i', isolate_file,
        '--config-variable', 'OS', 'win',
        '--config-variable', 'chromeos', '0',
        '-s', isolated_file,
      ]
      self.assertEqual(0, isolate.CMDcheck(isolate.OptionParserIsolate(), cmd))
      with open(isolated_file, 'rb') as f:
        actual = json.load(f)
      mapped = [
        os.path.join(u'files2', 'subdir', '42.txt'),
        os.path.join(u'files2', 'test_file1.txt'),
        os.path.join(u'files2', 'test_file2.txt'),
        os.path.join(u'symlink_full.py'),
      ]
      files = dict(
          (
            f,
            {
              u'h': unicode(hash_file('tests', 'isolate', f)),
              u's': _size('tests', 'isolate', f),
            }
          )
          for f in mapped)
      expected = {
        u'algo': u'sha-1',
        u'command': [u'python', u'symlink_full.py'],
        u'files': files,
        u'os': u'win',
        u'relative_cwd': u'.',
        u'version': unicode(isolate.isolateserver.ISOLATED_FILE_VERSION),
      }
      self.assertEqual(expected, actual)

  def test_CMDrun_extra_args(self):
    cmd = [
      'run',
      '--isolate', 'blah.isolate',
      '--outdir', os.path.join(self.cwd, 'jumbo'),
      '--', 'extra_args',
    ]
    self.mock(isolate, 'load_complete_state', self.load_complete_state)
    self.mock(isolate.subprocess, 'call', lambda *_, **_kwargs: 0)
    self.assertEqual(0, isolate.CMDrun(isolate.OptionParserIsolate(), cmd))


if __name__ == '__main__':
  logging.basicConfig(
      level=logging.DEBUG if '-v' in sys.argv else logging.ERROR,
      format='%(levelname)5s %(filename)15s(%(lineno)3d): %(message)s')
  if '-v' in sys.argv:
    unittest.TestCase.maxDiff = None
  unittest.main()
