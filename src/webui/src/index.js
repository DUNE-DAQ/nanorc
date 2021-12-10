import React from 'react';
import ReactDOM from 'react-dom';
import * as serviceWorker from './serviceWorker';
import Bootstrap from './bootstrap'
import TreeView from './tree'
import eventBus from './EventBus';
import OutputForm from './forms';
import {faidbadge, faFile } from '@fortawesome/free-regular-svg-icons'


function DisplayTree() {
  return (
      <nav className="sb-sidenav accordion sb-sidenav-light" id="sidenavAccordion">
                  <div id="tree">
                          <div className="treecontainertop">
                            Node browser
                          </div>
                          <div id="treecontainer1">
                              <TreeView treeUrl="/nanorcrest/tree" idkey="module" />
                          </div>
                          {/* <div className="treecontainertop">
                            Jobconf browser
                          </div>
                          <div id="treecontainer2">
                              <TreeView treeUrl="/urlModconfTree" idkey="config" />
                          </div> */}
                  </div>
              </nav>
  );
}

ReactDOM.render(
  <Bootstrap />,document.getElementById('bootstrap')
);
ReactDOM.render(
    <DisplayTree />,document.getElementById('treesector')
  );
ReactDOM.render(
    <OutputForm statusUrl="/nanorcrest/status" nodeUrl="/nanorcrest/node/listrev" />,document.getElementById('formsector')
  );

// If you want your app to work offline and load faster, you can change
// unregister() to register() below. Note this comes with some pitfalls.
// Learn more about service workers: https://bit.ly/CRA-PWA
serviceWorker.unregister();
