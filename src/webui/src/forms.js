import React, {useEffect, useState} from 'react';
import './index.css';
import 'bootstrap/dist/css/bootstrap.min.css';
import { Button, ButtonGroup,Container, Row, Col, InputGroup, FormControl, Form } from 'react-bootstrap';
//import Button from 'react-bootstrap/Button';
//import ButtonGroup from 'react-bootstrap/ButtonGroup';
//import Stack from 'react-bootstrap/Stack';
import eventBus from './EventBus';
import axios from 'axios';
import 'semantic-ui-less/semantic.less'
import { JsonToTable } from "react-json-to-table";

function simulateNetworkRequest() {
  return new Promise((resolve) => setTimeout(resolve, 2000));
}


class OutputForm extends React.Component {
  state = {
    status: {},
    reply: {},
    name:'',
    parentPath:'',
    disableControl:false,
  };
    constructor(props) {
        super(props);
        this.handleSubmit = this.handleSubmit.bind(this);
        this.input = React.createRef();
        this.link = React.createRef();
    }

    componentDidMount() {
      eventBus.on("module", (data) => this.fetchForm(data));
      eventBus.on("control", (data) => this.enablecontrol(data));
    }
    
    sendCommand= async (p) => {
      const modes = {
        "command": p,
        "logs": "",
        "path": null,
        "return_code": 0
      }
      
      console.log(modes)
      return modes.data
    }

    LoadingButton  = (p) => {
      const [isLoading, setLoading] = useState(p.self.state.disableControl);
      useEffect(() => {
        if (isLoading) {
          const sendCommand = async () => {
            const json = {
              "data": {
                  "command": "BOOT"
              },
              'Authorization': 'Basic ' + btoa('fooUsr:barPass')
          }
            //const modes = await axios.post("/nanorcrest/command"{data:'command='+p.label}, { auth: {username: 'fooUsr',password: 'barPass'}});
            const modes = await axios.post("/nanorcrest/command", json);
            console.log(modes);
            modes.data={
              "command": "BOOT",
              "logs": "",
              "path": null,
              "return_code": 0
            }
            p.self.setState({ reply: modes.data });      
        };
        sendCommand();
        setLoading(false);
        p.self.setState({ disableControl: false });
        }
      }, [p.self.state.disableControl]);
    
      const handleClick = () => {
        setLoading(true)
        p.self.setState({ disableControl: true });
      }
    
      return (
        <Button
          variant="outline-dark"
          size="lg"
          disabled={p.self.state.disableControl}
          onClick={!p.self.state.disableControl ? handleClick : null}
        >
          {isLoading ? 'Sending…' : p.label}
        </Button>
      );
    }

    enablecontrol(data){
        if(data.value){
          this.setState({ disableControl: true });
        }else{
          this.setState({ disableControl: false });
        }
    }

    fetchStatus = async path => {
      //const modes = await axios.get(path, {}, {auth: {username: 'fooUsr',password: 'barPass'}});
      const modes = {data:""};
      modes.data = {"apparatus_id": "listrev",
      "children": [
        {
          "children": [
            {
              "alive": true,
              "last_cmd_failed": false,
              "last_ok_cmd": "init",
              "last_sent_cmd": "init",
              "name": "lr1",
              "ping": true
            },
            {
              "alive": true,
              "last_cmd_failed": false,
              "last_ok_cmd": "init",
              "last_sent_cmd": "init",
              "name": "lr2",
              "ping": true
            }
          ],
          "name": "listrev"
        }
      ],
      "name": "listrev"
    }
      this.setState({
          status: modes.data.children[0],
          })
  }

    fetchForm(name){
      this.setState({ parentPath: name.parentPath })
      this.setState({ name: name.label })
      if (typeof name.parentPath==='undefined' || name.parentPath==''){
        this.fetchStatus(this.props.statusUrl);
      }else{
        this.fetchStatus(this.props.nodeUrl+'.'+name.parentPath+'.'+name.label);
      }
      
      //this.fetchStatus()
      //console.log(this.state.parentPath+'.'+name.label);

    }

    handleSubmit({formData}) {
      axios.post('/uploadJson', {'parentPath': this.state.parentPath, 'formData': formData, 'name':this.state.name,'schema':this.state.schema})
      .then(response => eventBus.dispatch('treechange', { data: response.data }))
      .catch(error => {
          this.setState({ errorMessage: error.message });
          console.error('There was an error!', error);
      });
    }

   

    render() {
      if (this.state.parentPath=='') {
        return (
          <main className="mainBlock">
            <div id="name" className="mt-1 mb-1 treetop"><h5>Selected: {this.state.name}</h5></div>
            <div id="detailPage" className="content default"><div className="card mb-2"></div>
            </div>
          </main>

        );
      }
      if (typeof this.state.parentPath==='undefined') {
        return (
          <main className="mainBlock">
            <div id="name" className="mt-1 mb-1 treetop"><h5>Selected: {this.state.name}</h5></div>
            <div id="detailPage" className="content default"><div className="card mb-2"></div>
            <Container>
            <Row>
            <Col>
            <InputGroup className="mb-3">
            <FormControl
              placeholder="Runnumber"
              aria-label="Runnumber"
              aria-describedby="basic-addon1"
            />
            </InputGroup>
            </Col>
            <Col>
            <select class="custom-select">
              <option selected>Run type</option>
              <option value="1">TEST</option>
              <option value="2">Foo</option>
              <option value="3">Bar</option>
            </select>
            </Col>
            </Row>
            <Row>
            <Col xs={2}>
            <ButtonGroup variant="dark" vertical="true">
            <this.LoadingButton label='Boot' self={this}/><br></br>
            <this.LoadingButton label='Init' self={this}/><br></br>
            <this.LoadingButton label='Conf' self={this}/><br></br>
            <this.LoadingButton label='Start' self={this}/><br></br>
            <this.LoadingButton label='Stop' self={this}/><br></br>
            <this.LoadingButton label='Scrap' self={this}/><br></br>
            <this.LoadingButton label='Terminate' self={this}/><br></br>
            </ButtonGroup>
            </Col>
            <Col><label>Reply:</label>
            <JsonToTable json={this.state.reply} />
            </Col>
            <Col></Col>
            </Row>
            <Row>
            <Col>
            <label>Status:</label>
            <JsonToTable json={this.state.status} />
            </Col>
            <Col></Col>
            </Row>
            </Container>
            </div>
          </main>

        );
      }
      return (   
        <main className="mainBlock">
            <div id="name" className="mt-1 mb-1 treetop"><h5>Selected: {this.state.name}</h5></div>
            <div id="detailPage" className="content default"><div className="card mb-2"></div>
            <Container>
            <Row>
            <Col>
            <label>Status:</label>
            <JsonToTable json={this.state.status} />
            </Col>
            <Col></Col>
            </Row>
            </Container>
            </div>
          </main>
    );
        
    }
}

const log = (type) => console.log.bind(console, type);

  
  export default OutputForm;