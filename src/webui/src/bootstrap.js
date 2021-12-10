import React, {useEffect, useState} from 'react';
import './index.css';
import 'bootstrap/dist/css/bootstrap.min.css';
import DropdownButton from 'react-bootstrap/DropdownButton';
import Dropdown from 'react-bootstrap/Dropdown';
import eventBus from './EventBus';
import { Button, ButtonGroup,Container, Row, Col, InputGroup, FormControl } from 'react-bootstrap';

function simulateNetworkRequest() {
    return new Promise((resolve) => setTimeout(resolve, 2000));
  }
  

function LoadingButton(){
    const [isLoading, setLoading,] = useState(false);
    const [inControl, setControl,] = useState(false);

  useEffect(() => {
    if (isLoading) {
      simulateNetworkRequest().then(() => {
        setLoading(false);
        console.log(inControl)
        if(inControl){
            setControl(false)
            eventBus.dispatch("control", { value: false });
        }else{
            setControl(true);
            eventBus.dispatch("control", { value: true }); 
        }      
      });
    }
  }, [isLoading]);

  const handleClick = () => setLoading(true);
  if (inControl){
    return (
        <Button
          variant="outline-light"
          disabled={isLoading}
          onClick={!isLoading ? handleClick : null}
        >
          {isLoading ? 'Releasing control...' : 'Release control'}
        </Button>
      );
  }
  return (
    <Button
      variant="outline-light"
      disabled={isLoading}
      onClick={!isLoading ? handleClick : null}
    >
      {isLoading ? 'Taking control...' : 'Take control'}
    </Button>
  );
}

function Bootstrap() {
    return (
        <nav className="d-flex justify-content-between sb-topnav navbar navbar-expand navbar-dark bg-dark">
            <div className="navbar-brand-container">
                <a className="navbar-brand" href="">  NANORC Web UI </a><br/>
                <div className="navbar-brand-desc"> DUNE DAQ Run control </div>
            </div>
            <LoadingButton />
            <ul className="navbar-nav ml-auto ml-md-0">
              
               
                <li className="nav-item dropdown w-auto">
                <DropdownButton variant="outline-light" title="">
                    <Dropdown.Item href="#/action-2">Logout</Dropdown.Item>
                    <Dropdown.Item href="#/action-3">Help</Dropdown.Item>
                </DropdownButton>
                </li>
                <li className="nav-item w-auto nav-item-light">
                    <br></br>
                </li>
                <li className="nav-item w-auto nav-item-light">
                    <div className="small">Logged in as:</div> usr
                </li>
            </ul>
        </nav>
    );
  }
  
  export default Bootstrap;
