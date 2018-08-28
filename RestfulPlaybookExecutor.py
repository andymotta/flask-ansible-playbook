from flask import Flask, jsonify, abort
# from restapp import app
from ansible.vars.manager import VariableManager
from ansible.inventory.manager import InventoryManager
from ansible.playbook.play import Play
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.parsing.dataloader import DataLoader
from ansible.executor.playbook_executor import PlaybookExecutor
from collections import namedtuple
from ansible.plugins.callback import CallbackBase
from ansible.errors import AnsibleError, AnsibleParserError, AnsibleFileNotFound
import os

#########################
# Manage Ansible STDOUT #
#########################

class ResultCallback(CallbackBase):
    """A sample callback plugin used for performing an action as results come in
    If you want to collect all results into a single object for processing at
    the end of the execution, look into utilizing the ``json`` callback plugin
    or writing your own custom callback plugin
    """
    def __init__(self):
        super(ResultCallback, self).__init__()
        # store all results
        self.results = []

    def v2_runner_on_ok(self, result, **kwargs):
        """
        This method could store the result in an instance attribute for retrieval later
        """
        host = result._host
        task = result._task
        output = result._result
        if result._result.get('changed', False):
            status = 'changed'
        else:
            status = 'ok'
        self.results.append({"host": host.name, "action":task.action, "status":status, "output": output})

    def v2_runner_on_failed(self, result, ignore_errors=False):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        host = result._host
        task = result._task
        output = result._result
        status = 'failed'
        self.results.append({"host": host.name, "action":task.action, "status":status, "output": output})

    def v2_runner_on_skipped(self, result):
        host = result._host
        task = result._task
        output = ''
        status = 'skipped'
        self.results.append({"host": host.name, "action":task.action, "status":status, "output": output})

    def v2_runner_on_unreachable(self, result):
        host = result._host
        task = result._task
        output = ''
        status = 'unreachable'
        self.results.append({"host": host.name, "action":task.action, "status":status, "output": output})

    def v2_runner_on_no_hosts(self, task):
        host = 'no host matched'
        task = task
        output = ''
        status = 'skipped'
        self.results.append({"host": "no host matched", "action":task, "status":"skipped", "output": output})


############################################
#        REST call to Ansible API          #
############################################
app = Flask(__name__)

@app.route('/')
def ansible():
    """Run Ansible playbook"""
    # initialize needed objects
    loader = DataLoader()
    # create inventory, use path to host config file as source or hosts in a comma separated string
    inventory = InventoryManager(loader=loader, sources='hosts')
    # variable manager takes care of merging all the different sources to give you a unifed view of variables available in each context
    variable_manager = VariableManager(loader=loader, inventory=inventory)
    # variable_manager.extra_vars = {'ansible_user': 'ansible', 'ansible_port': '5986', 'ansible_connection': 'local',
    #                                'ansible_password': 'pass'}  # Here are the variables used in the playbook
    passwords = dict(vault_pass='secret')

    # since API is constructed for CLI it expects certain options to always be set, named tuple 'fakes' the args parsing options object
    Options = namedtuple('Options',
                         ['listtags', 'listtasks', 'listhosts', 'syntax', 'connection', 'module_path', 'forks',
                          'remote_user', 'private_key_file', 'ssh_common_args', 'ssh_extra_args', 'sftp_extra_args',
                          'scp_extra_args', 'become', 'become_method', 'become_user', 'verbosity', 'check', 'diff'])
    options = Options(listtags=False, listtasks=False, listhosts=False, syntax=False, connection='local',
                      module_path=None, forks=100, remote_user='slotlocker', private_key_file=None,
                      ssh_common_args=None, ssh_extra_args=None, sftp_extra_args=None, scp_extra_args=None, become=None,
                      become_method=None, become_user=None, verbosity=None, check=False, diff=False)

    # Instantiate our ResultCallback for handling results as they come in. Ansible expects this to be one of its main display outlets
    results_callback = ResultCallback()

    playbook_path = 'myplaybook.yml'
    if not os.path.exists(playbook_path):
        raise AnsibleFileNotFound("Playbook %s does not exist" % playbook_path)
    pbex = PlaybookExecutor(playbooks=[playbook_path], inventory=inventory, variable_manager=variable_manager,
                            loader=loader, options=options, passwords=passwords)

    # Use our json callback instead of the ``default`` callback plugin, which prints to stdout
    pbex._tqm._stdout_callback = results_callback

    try:
        results = pbex.run()
    except AnsibleParserError as e:
        raise AnsibleError(e)
    # Return a json representation of the playbook run
    return jsonify({'Playbook Results': [Task for Task in results_callback.results]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True, use_reloader=False)