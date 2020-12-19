#
# program.py
#
# The Pashmak Project
# Copyright 2020 parsa shahmaleki <parsampsh@gmail.com>
#
# This file is part of Pashmak.
#
# Pashmak is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Pashmak is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Pashmak.  If not, see <https://www.gnu.org/licenses/>.
#########################################################################

""" Pashmak program object """

import sys
import os
import signal
from pathlib import Path
from core import parser
from core import helpers, version, modules
from core.class_system import Class

import hashlib, time, random, datetime

class Program(helpers.Helpers):
    """ Pashmak program object """

    def __init__(self, is_test=False, args=[]):
        self.states = [{
            'current_step': 0,
            'commands': [],
            'vars': {
                'argv': args,
                'argc': len(args)
            }
        }] # list of states
        self.functions = {
            "mem": [], # mem is a empty function just for save mem in code
            "rmem": [],
        } # declared functions <function-name>:[<list-of-body-commands>]
        self.sections = {} # list of declared sections <section-name>:<index-of-command-to-jump>
        self.classes = {} # list of declared classes
        self.imported_files = [] # list of imported files
        self.mem = None # memory temp value
        self.is_test = is_test # program is in testing state
        self.output = '' # program output (for testing state)
        self.runtime_error = None # program raised error (for testing state)
        self.try_endtry = [] # says program is in try-endtry block
        self.namespaces_tree = [] # namespaces tree
        self.used_namespaces = [] # list of used namespaces
        self.included_modules = [] # list of included modules to stop repeating imports

        self.allowed_pashmak_extensions = ['pashm']

        self.states[-1]['current_step'] = 0
        self.stop_after_error = True
        self.main_filename = os.getcwd() + '/__main__'

        # set argument variables
        self.set_var('argv', args)
        self.set_var('argc', len(self.get_var('argv')))

    def import_script(self, paths, import_once=False):
        """ Imports scripts/modules """
        op = self.states[-1]['commands'][self.states[-1]['current_step']]

        if type(paths) == str:
            paths = [paths]
        elif type(paths) != list and type(paths) != tuple:
            return self.raise_error('ArgumentError', 'invalid argument type', op)

        for path in paths:
            code_location = path
            if path[0] == '@':
                code_location = path
                module_name = path[1:]
                try:
                    namespaces_prefix = ''
                    for part in self.namespaces_tree:
                        namespaces_prefix += part + '.'
                    namespaces_prefix += '@'
                    if not namespaces_prefix + module_name in self.included_modules:
                        content = modules.modules[module_name]
                        # add this module to imported modules
                        self.included_modules.append(namespaces_prefix + module_name)
                    else:
                        return
                except KeyError:
                    return self.raise_error('ModuleError', 'undefined module "' + module_name + '"', op)
            else:
                if path[0] != '/':
                    path = os.path.dirname(os.path.abspath(self.main_filename)) + '/' + path
                if os.path.abspath(path) in self.imported_files and import_once:
                    return
                try:
                    content = open(path, 'r').read()
                    content = '$__ismain__ = False; $__file__ = "' + path.replace('\\', '\\\\') + '";\n$__dir__ = "' + os.path.dirname(path).replace('\\', '\\\\') + '"\n' + content
                    content += '\n$__file__ = "' + self.get_var('__file__').replace('\\', '\\\\') + '"'
                    content += '\n$__dir__ = "' + self.get_var('__dir__').replace('\\', '\\\\') + '"'
                    content += '\n$__ismain__ = "' + str(bool(self.get_var('__ismain__'))) + '"'
                    code_location = path
                    self.imported_files.append(os.path.abspath(code_location))
                except FileNotFoundError as ex:
                    return self.raise_error('FileError', str(ex), op)
                except PermissionError as ex:
                    return self.raise_error('FileError', str(ex), op)

            commands = parser.parse(content, filepath=code_location)
            self.exec_func(commands, False)

    def set_commands(self, commands: list):
        """ Set commands list """
        # include stdlib before everything
        tmp = parser.parse('''
        $__file__ = "''' + os.path.abspath(self.main_filename).replace('\\', '\\\\') + '''"
        $__dir__ = "''' + os.path.dirname(os.path.abspath(self.main_filename)).replace('\\', '\\\\') + '''"
        $__ismain__ = True
        mem self.import_script('@stdlib')
        ''', filepath='<system>')
        commands.insert(0, tmp[0])
        commands.insert(1, tmp[1])
        commands.insert(2, tmp[2])
        commands.insert(3, tmp[3])

        # set commands on program object
        self.states[-1]['commands'] = commands

    def set_command_index(self, op: dict) -> dict:
        """ Add command index to command dictonary """
        op['index'] = self.states[-1]['current_step']
        return op

    def get_mem(self):
        """ Return memory value and empty that """
        mem = self.mem
        self.mem = None
        return mem

    def update_section_indexes(self, after_index):
        """
        When a new command inserted in commands list,
        this function add 1 to section indexes to be
        sync with new commands list
        """
        for k in self.sections:
            if self.sections[k] > after_index:
                self.sections[k] = self.sections[k] + 1
        i = 0

    def raise_error(self, error_type: str, message: str, op: dict):
        """ Raise error in program """
        # check is in try
        if self.try_endtry:
            section_index = self.try_endtry[-1]
            self.try_endtry.pop()
            new_step = self.sections[str(section_index)]
            self.states[-1]['current_step'] = new_step-1

            # put error data in mem
            self.mem = {'type': error_type, 'message': message, 'index': op['index']}
            return
        # raise error
        if self.is_test:
            self.runtime_error = {'type': error_type, 'message': message, 'index': op['index']}
            if self.stop_after_error:
                self.states[-1]['current_step'] = len(self.states[-1]['commands'])*2
            return

        # render error
        print(error_type + ': ' + message + ':')
        last_state = self.states[0]
        for state in self.states[1:]:
            try:
                if last_state:
                    tmp_op = last_state['commands'][last_state['current_step']]
                else:
                    tmp_op = state['commands'][0]
                print(
                    '\tin ' + tmp_op['file_path'] + ':' + str(tmp_op['line_number'])\
                    + ': ' + tmp_op['str']
                )
            except KeyError:
                pass
            last_state = state
        print('\tin ' + op['file_path'] + ':' + str(op['line_number']) + ': ' + op['str'])
        sys.exit(1)

    def exec_func(self, func_body: list, with_state=True, default_variables={}):
        """ Gets a list from commands and runs them as function or included script """
        # create new state for this call
        if with_state:
            state_vars = dict(self.states[-1]['vars'])
        else:
            state_vars = self.states[-1]['vars']

        for k in default_variables:
            state_vars[k] = default_variables[k]
        self.states.append({
            'current_step': 0,
            'commands': func_body,
            'vars': state_vars,
        })

        # run function
        self.start_state()

    def eval(self, command, only_parse=False):
        """ Runs eval on command """
        i = 0
        command = command.strip()
        is_in_string = False
        command_parts = [[False, '']]
        while i < len(command):
            is_string_start = False
            if command[i] == '"' or command[i] == "'":
                before_backslashes_count = 0
                try:
                    x = i-1
                    while x >= 0:
                        if command[x] == '\\':
                            before_backslashes_count += 1
                        else:
                            x = -1
                        x -= 1
                except:
                    pass
                if is_in_string:
                    if before_backslashes_count % 2 != 0 and before_backslashes_count != 0:
                        pass
                    elif is_in_string == command[i]:
                        is_in_string = False
                        command_parts[-1][1] += command[i]
                        is_string_start = True
                        command_parts.append([False, ''])
                else:
                    is_in_string = command[i]
                    command_parts.append([True, ''])
                    command_parts[-1][1] += command[i]
                    is_string_start = True
            if not is_string_start:
                command_parts[-1][1] += command[i]
            i += 1

        full_op = ''
        opened_inline_calls_count = 0
        for code in command_parts:
            if code[0] == False:
                code = code[1]
                # replace variable names with value of them
                variables_in_code = []
                literals = '()+-/*%=}{<> [],'
                code_words = self.multi_char_split(code, literals)
                for word in code_words:
                    if word:
                        if word[0] == '$' and not '@' in word:
                            variables_in_code.append(word[1:])
                for k in variables_in_code:
                    self.variable_required(k, self.states[-1]['commands'][self.states[-1]['current_step']])
                    code = code.replace('$' + k, 'self.get_var("' + k + '")')
                code = code.replace('->', '.')
                code = code.replace('^', 'self.get_mem()')
                z = 0
                new_code = ''
                while z < len(code):
                    if z > 0:
                        if code[z-1] + code[z] == '%{':
                            if opened_inline_calls_count == 0:
                                new_code = new_code[:len(new_code)-1]
                                new_code += 'self.call_inline_func("""'
                                pass # replace
                            else:
                                new_code += code[z]
                            opened_inline_calls_count += 1
                        elif code[z-1] + code[z] == '}%':
                            if opened_inline_calls_count <= 1:
                                new_code = new_code[:len(new_code)-1]
                                new_code += '""")'
                            else:
                                new_code += code[z]
                            opened_inline_calls_count -= 1
                        else:
                            new_code += code[z]
                    else:
                        new_code += code[z]
                    z += 1
                code = new_code
            else:
                code = code[1]
            full_op += code
        if only_parse:
            return full_op
        return eval(full_op)

    def call_inline_func(self, code: str):
        """ Runs the internal function call "%{ func_or_command }" """
        commands = parser.parse(code)
        self.exec_func(commands, False)
        return self.get_mem()

    def run(self, op: dict):
        """ Run once command """

        op = self.set_command_index(op)
        op_name = op['command']

        if op_name == 'endfunc':
            self.run_endfunc(op)
            return

        if op_name == 'endclass':
            self.run_endclass(op)
            return

        # if a function is started, append current command to the function body
        try:
            self.current_func
            try:
                self.current_class
                self.classes[self.current_class].methods[self.current_func].append(op)
            except:
                self.functions[self.current_func].append(op)
            return
        except NameError:
            pass
        except KeyError:
            pass
        except AttributeError:
            pass

        # list of commands
        commands_dict = {
            'free': self.run_free,
            'read': self.run_read,
            'func': self.run_func,
            'goto': self.run_goto,
            'gotoif': self.run_gotoif,
            'isset': self.run_isset,
            'try': self.run_try,
            'endtry': self.run_endtry,
            'namespace': self.run_namespace,
            'endnamespace': self.run_endnamespace,
            'use': self.run_use,
            'class': self.run_class,
            'endclass': self.run_endclass,
            'new': self.run_new,
            'return': self.run_return,
            'pass': None,
            'if': None,
            'elif': None,
            'else': None,
            'endif': None,
        }

        # check op_name is a valid command
        op_func = 0
        try:
            op_func = commands_dict[op_name]
        except:
            pass

        # if op_name is a valid command, run the function
        if op_func != 0:
            if op_func != None:
                op_func(op)
            return

        # check command syntax is variable value setting
        tmp_bool = True
        if op['str'][0] == '$':
            tmp_parts = op['str'].strip().split('@', 1)
            if self.variable_exists(tmp_parts[0].strip()[1:]) and len(tmp_parts) > 1:
                tmp_bool = False

        if op['str'][0] == '$' and tmp_bool:
            # if a class is started, append current command as a property to class
            is_in_class = False
            try:
                self.current_class
                is_in_class = True
            except NameError:
                pass
            except KeyError:
                pass
            except AttributeError:
                pass
            parts = op['str'].strip().split('=', 1)
            varname = parts[0].strip()
            full_varname = varname
            varname = varname.split('->', 1)
            is_class_setting = False
            if len(varname) > 1:
                is_class_setting = varname[1].replace('->', '.props.')
            varname = varname[0]
            if len(parts) <= 1:
                if is_in_class:
                    self.classes[self.current_class].props[varname[1:]] = None
                else:
                    self.set_var(varname[1:], None)
                return
            value = None
            if True:
                value = self.eval(parts[1].strip())
            if is_class_setting != False:
                tmp_real_var = self.eval(varname)
                exec('tmp_real_var.props.' + is_class_setting + ' = value')
            else:
                if is_in_class:
                    self.classes[self.current_class].props[varname[1:]] = value
                else:
                    if '[' in varname or ']' in varname:
                        the_target = self.eval(varname, only_parse=True)
                        exec(the_target + ' = value')
                    else:
                        self.set_var(varname[1:], value)
            return

        # check function exists
        is_method = False
        if op['command'][0] == '$':
            var_name = op['command'].split('@')[0]
            var = self.all_vars()[var_name[1:]]
            if type(var) != Class:
                return self.raise_error('MethodError', 'calling method on non-class object "' + var_name + '"', op)
            try:
                func_body = var.methods[op['command'].split('@')[1]]
                is_method = var
            except:
                return self.raise_error('MethodError', 'class ' + self.all_vars()[var_name[1:]].__name__ + ' has not method "' + op['command'][0].split('@')[1] + '"', op)
        else:
            try:
                func_body = self.functions[self.current_namespace() + op_name]
            except KeyError:
                func_body = None
                for used_namespace in self.used_namespaces:
                    try:
                        func_body = self.functions[used_namespace + '.' + op_name]
                    except KeyError:
                        pass
                if not func_body:
                    try:
                        func_body = self.functions[op_name]
                    except KeyError:
                        return self.raise_error('SyntaxError', 'undefined function "' + op_name + '"', op)

        # run function
        try:
            # put argument in the mem
            if op['args_str'] != '':
                if op['command'] != 'rmem':
                    self.mem = self.eval(op['args_str'])
                else:
                    self.eval(op['args_str'])
            else:
                self.mem = ''

            # execute function body
            with_state = True
            if op_name in ['import', 'mem', 'python', 'rmem', 'eval']:
                with_state = False
            default_variables = {}
            if is_method != False:
                default_variables['this'] = is_method
            self.exec_func(func_body, with_state, default_variables=default_variables)
            return
        except Exception as ex:
            raise

    def bootstrap_modules(self):
        """ Loads modules from module paths in environment variable """
        try:
            os.environ['PASHMAKPATH']
        except:
            os.environ['PASHMAKPATH'] = ''
        home_directory = str(Path.home())
        os.environ['PASHMAKPATH'] = '/usr/lib/pashmak_modules:' + home_directory + '/.local/lib/pashmak_modules:' + os.environ['PASHMAKPATH']
        pashmak_module_paths = os.environ['PASHMAKPATH']
        paths = pashmak_module_paths.strip().split(':')
        paths = [path.strip() for path in paths if path.strip() != '']
        for path in paths:
            try:
                path_files = os.listdir(path)
            except:
                continue
            for f in path_files:
                module_name = None
                if os.path.isdir(path + '/' + f):
                    if os.path.isfile(path + '/' + f + '/__init__.pashm'):
                        module_name = f.split('/')[-1].split('.')[0]
                        f = path + '/' + f + '/__init__.pashm'
                    else:
                        f = path + '/' + f
                else:
                    f = path + '/' + f

                if f.split('.')[-1] in self.allowed_pashmak_extensions:
                    if os.path.isfile(f):
                        # check module exists
                        f_name = f.split('/')[-1]
                        if module_name == None:
                            module_name = f_name.split('.')[0]
                        try:
                            modules.modules[module_name]
                        except:
                            # module not found, we can add this
                            try:
                                fo = open(f, 'r')
                                content = fo.read()
                                fo.close()
                                content = '$__file__ = "' + os.path.abspath(f).replace('\\', '\\\\') + '";\n$__dir__ = "' + os.path.dirname(os.path.abspath(f)).replace('\\', '\\\\') + '";\n' + content
                                modules.modules[module_name] = content
                            except:
                                raise
                                pass

    def start_state(self):
        """ Start running state thread """
        is_in_func = False
        self.states[-1]['current_step'] = 0

        # load the sections
        i = 0
        while i < len(self.states[-1]['commands']):
            current_op = self.set_command_index(self.states[-1]['commands'][i])
            if current_op['command'] == 'section':
                if not is_in_func:
                    arg = current_op['args'][0]
                    self.sections[arg] = i+1
                    self.states[-1]['commands'][i] = parser.parse('pass', filepath='<system>')[0]
            elif current_op['command'] == 'func':
                is_in_func = True
            elif current_op['command'] == 'endfunc':
                is_in_func = False
            i += 1

        self.states[-1]['current_step'] = 0
        while self.states[-1]['current_step'] < len(self.states[-1]['commands']):
            try:
                self.run(self.states[-1]['commands'][self.states[-1]['current_step']])
            except Exception as ex:
                try:
                    self.set_command_index(self.states[-1]['commands'][self.states[-1]['current_step']])
                except:
                    break
                self.raise_error(
                    ex.__class__.__name__,
                    str(ex),
                    self.set_command_index(self.states[-1]['commands'][self.states[-1]['current_step']])
                )
            self.states[-1]['current_step'] += 1

        if len(self.states) > 1:
            self.states.pop()

    def start(self):
        """ Start running the program """

        signal.signal(signal.SIGINT, self.signal_handler)

        self.bootstrap_modules()

        self.start_state()
