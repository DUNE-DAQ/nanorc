from transitions import Machine
from functools import partial

class FSM(Machine):
    def __init__(self,console, fsm_type, verbose=False):
        if fsm_type == 'timing':
            self.states_cfg = [ "none", "booted", "initialised", "configured", "error", "running" ]
            self.transitions_cfg = [
                { "trigger": "boot",      "source": "none",        "dest": "booted"     },
                { "trigger": "init",      "source": "booted",      "dest": "initialised"},
                { "trigger": "conf",      "source": "initialised", "dest": "configured" },
                { "trigger": "start",     "source": "configured",  "dest": "running"    },
                { "trigger": "stop",      "source": "running",     "dest": "configured" },
                { "trigger": "scrap",     "source": "configured",  "dest": "initialised"},
                { "trigger": "terminate", "source": "*",           "dest": "none"       },
                { "trigger": "to_error",  "source": "*",           "dest": "error"      }
            ]

        else:
            self.states_cfg = [ "none", "booted", "initialised", "configured", "running", "paused", "error"]
            self.transitions_cfg = [
                { "trigger": "boot",      "source": "none",        "dest": "booted"     },
                { "trigger": "init",      "source": "booted",      "dest": "initialised"},
                { "trigger": "conf",      "source": "initialised", "dest": "configured" },
                { "trigger": "start",     "source": "configured",  "dest": "running"    },
                { "trigger": "stop",      "source": "running" ,    "dest": "configured" },
                { "trigger": "stop",      "source": "paused" ,     "dest": "configured" },
                { "trigger": "resume",    "source": "running",     "dest": "running"    },
                { "trigger": "resume",    "source": "paused",      "dest": "running"    },
                { "trigger": "pause",     "source": "running",     "dest": "paused"     },
                { "trigger": "pause",     "source": "paused",      "dest": "paused"     },
                { "trigger": "scrap",     "source": "configured",  "dest": "initialised"},
                { "trigger": "terminate", "source": "*",           "dest": "none"       },
                { "trigger": "to_error",  "source": "*",           "dest": "error"      }
            ]
        if verbose:
            print_friendly_transitions = set()
            for tr in self.transitions_cfg:
                if tr['trigger'] == 'to_error': continue
                print_friendly_transitions.add(tr['trigger'])
            console.print(f'FSM available states: {self.states_cfg}')
            console.print(f'FSM available transitions: {print_friendly_transitions}')
        self.acting_transitions = []
        self.finalisor_transitions = []

        transition_state_to_add = []
        transition_to_remove = []
        # we need to loop over transitions, because if they are long, new states are added
        for transition in self.transitions_cfg:
            matched_from = False
            matched_to = False
            for state in self.states_cfg:
                if transition['source'] == "*" or transition['source'] == state:
                    matched_from = True
                if transition['dest'] == "*" or transition['dest'] == state:
                    matched_to   = True
            if not matched_from or not matched_to:
                raise RuntimeError(f'Transitions \'{transition["trigger"]}\' doesn\'t match for either its source or destination state: \'{transition["source"]}\' -> \'{transition["dest"]}\', list of states: {self.states_cfg}')

            name = transition["trigger"]+"_ing"
            transition_state_to_add += [name]

            # add these new states
            self.acting_transitions.append({
                "trigger":transition["trigger"],
                "source": transition["source"],
                "dest": name
            })

            self.finalisor_transitions.append({
                "trigger":"end_"+transition["trigger"],
                "source": name,
                "dest": transition["dest"]
            })

            # remove the old direct transitions
            transition_to_remove.append(transition)

        states = self.states_cfg + transition_state_to_add
        super().__init__(states=states, initial=states[0], send_event=True)

        for transition in self.acting_transitions+self.finalisor_transitions:
            self.add_transition(transition["trigger"], transition["source"], transition["dest"])

    def _can_(self, transition, cls):
        if transition in self.finalisor_transitions:
            return False

        for t in self.acting_transitions:
            if t["trigger"] != transition:
                continue
            if cls.state == t["source"] or t['source'] == "*":
                return True

        return False

    def _get_dest(self, transition):
        for t in self.transitions_cfg:
            if t["trigger"] == transition:
                return t['dest']
        raise RuntimeError(f'Transition {transition} is not a transition in your toplevelcfg.json')

    def _checked_assignment(self, model, name, func):
        if not hasattr(model, name):
            setattr(model, name, func)

    def make_node_fsm(self, node):
        self._checked_assignment(node, "get_destination", self._get_dest)

        for tr in self.acting_transitions:
            function_name = 'on_enter_'+tr["dest"]
            if not getattr(node, function_name, None):
                setattr(node, function_name, node._on_enter_callback.__get__(node))
            function_name = 'on_exit_'+tr["dest"]
            if not getattr(node, function_name, None):
                setattr(node, function_name, node._on_exit_callback.__get__(node))

        for tr in self.acting_transitions+self.finalisor_transitions:
            new_method = partial(self._can_, tr["trigger"], node)
            function_name = "can_"+tr["trigger"]
            self._checked_assignment(node, function_name, new_method)

        super().add_model(node)
