from transitions import Machine

class FSMMachine(Machine):
    def __init__(self, cfg):
        self.states_cfg = cfg["states"]
        self.transitions_cfg= cfg["transitions"]
        self.acting_transitions = []
        self.finalisor_transitions = []
        
        transition_state_to_add = []
        transition_to_remove = []
        # we need to loop over transitions, because if they are long, new states are added
        for transition in self.transitions_cfg:
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

        states = self.states_cfg + transition_state_to_add + ["error"]
        super().__init__(states=states, initial=states[0], send_event=True)
        
        for transition in self.acting_transitions+self.finalisor_transitions:
            self.add_transition(transition["trigger"], transition["source"], transition["dest"])


    def add_node(self, model):
        for tr in self.acting_transitions:
            function_name = 'on_enter_'+tr["dest"]
            if not getattr(model, function_name, None):
                setattr(model, function_name, model._on_enter_callback.__get__(model))
            function_name = 'on_exit_'+tr["dest"]
            if not getattr(model, function_name, None):
                setattr(model, function_name, model._on_exit_callback.__get__(model))
        
        super().add_model(model)
