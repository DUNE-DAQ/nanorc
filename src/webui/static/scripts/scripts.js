var fsm = {};
var root = "";
var state = "";
var selectedNode = null;
function populateButtons(){
$( "#stateButtonsDiv" ).empty()
console.log(fsm)
  for(var key in fsm.transitions) {   
      if(fsm.transitions[key]['source']==state || fsm.transitions[key]['source']== '*'){
        if(fsm.transitions[key]['dest'] != 'error'){
          $("#stateButtonsDiv").append("<button id='"+fsm.transitions[key]['trigger']+"' class='green button control' style='margin:5px;'>"+fsm.transitions[key]['trigger']+"</button> &nbsp &nbsp");
          comm = fsm.transitions[key]['trigger']
        }
      }
  }
$(".control").click(function() {
  sendComm($(this).attr("id"),$("#runnumber").val(),$("#runtype").val());
}); 
}
function getTree(){
$.ajax({
  url: "http://"+serverhost+"/nanorcrest/tree",
  beforeSend: function(xhr) { 
    xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass")); 
  },
  type: 'GET',
  crossOrigin: true,
  crossDomain: true,
  dataType: "text",
  contentType:'text/plain',
  cors: true ,
  crossOrigin: true,
  success: function (d) {
    //d = JSON.stringify(d);
    d = d.replace(/name/g, "text");
    d = JSON.parse(d)
    root = d.text
  $('#controlTree').jstree(true).settings.core.data = d;
  $('#controlTree').jstree(true).refresh();
  },
  error: function(e){
    alert(JSON.stringify(e));
  }
});
}
function sendComm(command,runnumber, runtype){
  $("#state:text").val('Executing...')
  $(".control").attr("disabled", true);
  if(command == 'start'){
    dataload = {"command":command,"run_type":runtype,"run_num":runnumber,}
  }else{
    dataload= "command="+command
  }
  $.ajax({
      url: "http://"+serverhost+"/nanorcrest/command",
      beforeSend: function(xhr) { 
        xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass")); 
      },
      type: 'POST',
      data: dataload,
      success: function (d) {
        alert(JSON.stringify(d));
        getStatus()
        getTree()
      },
      error: function(e){
      console.log(e)
      }
  });
}
  function getStatus(){
    if(selectedNode==null){
        url = "http://"+serverhost+"/nanorcrest/status"
    }else{
      if(selectedNode.text==root){
        url = "http://"+serverhost+"/nanorcrest/status"
      }else{
        selText= selectedNode
        path=$('#controlTree').jstree(true).get_path(selText,".")
        path = path.replace(root+".", "");
        url = "http://"+serverhost+"/nanorcrest/node/"+path
      }
    }
    console.log(url)
    $.ajax({
        url: url,
        beforeSend: function(xhr) { 
          xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass")); 
        },
        type: 'GET',
        dataType: "text",
        success: function (d) {
          d = JSON.parse(d)
          $("#state:text").val(d.state)
          state = d.state
          populateButtons()
          $('#json-renderer').jsonViewer(d);
        },
        error: function(e){
          console.log(e)
        }
    });}
  function getFsm(){
  $.ajax({
      url: "http://"+serverhost+"/nanorcrest/fsm",
      beforeSend: function(xhr) { 
        xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass")); 
      },
      type: 'GET',
      dataType: "text",
      success: function (d) {
        d = JSON.parse(d)
        fsm = d

      },
      error: function(e){
        console.log(e)
      }
  });}

  $('#controlTree').on('changed.jstree', function () {
    selectedNode = $("#controlTree").jstree("get_selected",true)[0]
    getStatus()
    if(selectedNode != null){
      $("#selected").text('Selected: '+selectedNode.text)
    }else{
      $("#selected").text('Selected: '+root)
    }
    
  })
	$(window).resize(function () {
		var h = Math.max($(window).height() - 0, 420);
		 // $('#container, #data, #tree').height(h).filter('.default').css('height', h + 'px');
		 // h=h-200;
		 // $('#data .content').height(h).filter('.default').css('height', h + 'px');
	}).resize();
    $(document).ready(function() {
      getFsm()
      $.ajax({
        url: "http://localhost:5001/nanorcrest/tree",
        beforeSend: function(xhr) { 
          xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass")); 
        },
        type: 'GET',
        crossOrigin: true,
        crossDomain: true,
        dataType: "text",
        contentType:'text/plain',
        cors: true ,
        crossOrigin: true,
        success: function (d) {
          //d = JSON.stringify(d);
          d = d.replace(/name/g, "text");
          d = JSON.parse(d)
          root = d.text
          $('#controlTree').jstree({
            'plugins': ['types'],
            'types' : {
                    'default' : {
                    'icon' : '/static/pics/gray.png'
                    }
                },
            //'contextmenu': {
            //   'select_node': false,
            //   'items' : customMenu
            //},
            'core' : {
                'multiple': false,
                'data' : d,
      
            }
        });
        },
        error: function(e){
          alert(JSON.stringify(e));
        }
      });
      getStatus()
      $("#selected").text('Selected: '+root)
    })