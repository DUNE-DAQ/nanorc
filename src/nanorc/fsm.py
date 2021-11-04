from transitions import Machine

class FSMMachine(Machine):
    def __init__(self, cfg):
        self.states_cfg = cfg["states"]
        self.transitions_cfg= cfg["transitions"]
        
        long_transition_to_add = []
        transition_state_to_add = []
        states_after_long_transition = []
        long_transition_to_remove = []
        # we need to loop over transitions, because if they are long, new states are added
        for transition in self.transitions_cfg:
            name = transition["trigger"]+"_ing"
        
            transition_state_to_add.append(name)
            # add these new states
            long_transition_to_add.append({
                "trigger":transition["trigger"],
                "source": transition["source"],
                "dest": name
            })

            long_transition_to_add.append({
                "trigger":"end_"+transition["trigger"],
                "source": name,
                "dest": transition["dest"]
            })
            
            states_after_long_transition.append(transition["dest"])
            # remove the old direct transitions
            long_transition_to_remove.append(transition)

        states = self.states_cfg + transition_state_to_add + ["error"]
        super().__init__(states=states, initial=states[0])
        
        transition_to_include = self.transitions_cfg+long_transition_to_add
        for transition in transition_to_include:
            if transition in long_transition_to_remove:
                continue
            self.add_transition(transition["trigger"], transition["source"], transition["dest"])
