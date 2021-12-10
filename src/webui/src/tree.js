import React, { useState, useEffect } from 'react';
import CheckboxTree from 'react-checkbox-tree';
//import './index.css';
import axios from 'axios';
//import './tree.css';
import 'react-checkbox-tree/lib/react-checkbox-tree.css';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faSun, faFile } from '@fortawesome/free-regular-svg-icons'
import { library } from '@fortawesome/fontawesome-svg-core'
import eventBus from './EventBus';

library.add(faSun, faFile)


class TreeView extends React.Component {
    state = {
        checked: [],
        expanded: [],
        clicked: {},
        filterText: '',
        nodesFiltered: [],
        nodes: [],
        isLoading: false,
    };

 
    constructor(props) {
        super(props);
        this.onCheck = this.onCheck.bind(this);
        this.onClick = this.onClick.bind(this);
        this.onExpand = this.onExpand.bind(this);
        this.onFilterChange = this.onFilterChange.bind(this);
        this.filterTree = this.filterTree.bind(this);
        this.filterNodes = this.filterNodes.bind(this);
        //this.isLoading = this.isLoading.bind(this);
    }

    fetchTree = async () => {
        //const modes = await axios.get(this.props.treeUrl, {}, {auth: {username: 'fooUsr',password: 'barPass'}});
        const modes = {data:""};
        //console.log(modes.data.children[0])
        modes.data={
            "children": [
              {
                "children": [
                  {
                    "label": "lr1",
                    "value": "lr1"
                  },
                  {
                    "label": "lr2",
                    "value": "lr2"
                  }
                ],
                "label": "listrev",
                "value": "listrev"
              }
            ],
            "name": "listrev"
          }
        this.setState({
            nodes: [modes.data.children[0]],
            nodesFiltered:[modes.data.children[0]],
            isLoading: false
            })
    }
    async componentDidMount() {
        this.setState({ isLoading: true });
        await this.fetchTree()
        eventBus.on("treechange", (data) => this.fetchTree(),
        );
    }
    onCheck(checked) {
        this.setState({ checked });
    }

    onClick(clicked) {
        this.setState({ clicked });
        var parentPath = this.getFullPath(this.state.nodesFiltered, clicked.parent.value)
        eventBus.dispatch(this.props.idkey, { value: clicked.value, label:clicked.label, parentPath:parentPath });
    }

    onExpand(expanded) {
        this.setState({ expanded });
    }

    onFilterChange(e) {
        this.setState({ filterText: e.target.value }, this.filterTree);
    }
    getFullPath(arr, target) {
        for (let i = 0; i < arr.length; i++) {
          if (arr[i].value === target) {
            return arr[i].value;
          }
          if (!arr[i].children) {
            continue;
          }
          var path = this.getFullPath(arr[i].children, target);
          if (path) {
            return arr[i].value + "." + path;
          }
        }
      }

    filterTree() {
        // Reset nodes back to unfiltered state
        if (!this.state.filterText) {
            this.setState((prevState) => ({
                nodesFiltered: prevState.nodes,
            }));

            return;
        }
        
            const nodesFiltered = (prevState) => ( 
                {nodesFiltered: prevState.nodes.reduce(this.filterNodes, []) }
            );
            this.setState(nodesFiltered);
       
    }

    filterNodes(filtered, node) {
        const { filterText } = this.state;
        const children = (node.children || []).reduce(this.filterNodes, []);

        if (
            // Node's label matches the search string
            node.label.toLocaleLowerCase().indexOf(filterText.toLocaleLowerCase()) > -1 ||
            // Or a children has a matching node
            children.length
        ) {
            filtered.push({...node, ...children.length && {children}});
        }

        return filtered;
    }
    stateChecker(){
        return [this.props.key, (this.state.clicked || null)]
    }
    render() {
        const { checked, expanded, clicked,filterText, nodesFiltered} = this.state;
        const notClickedText = '(none)';
        
        if (this.state.isLoading) {
            return <p>Loading...</p>;
        }

        return (
            <div className="clickable-labels">
                <input
                    className="filter-text"
                    placeholder="Search..."
                    type="text"
                    value={filterText}
                    onChange={this.onFilterChange}
                />
                <CheckboxTree
                    
                    checked={checked}
                    expanded={expanded}
                    nodes={nodesFiltered}
                    expandOnClick = {false}
                    onCheck={this.onCheck}
                    onClick={this.onClick}
                    onExpand={this.onExpand}
                    //onlyLeafCheckboxes={true}
                    //nativeCheckboxes={true}
                    icons={{
                        leaf: <FontAwesomeIcon className="rct-icon rct-icon-leaf-close" icon={["far", "sun"]} />
                    }}
                />
                
            </div>
        );
    }
    
}

  
  export default TreeView;
