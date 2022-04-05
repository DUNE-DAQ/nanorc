var fsm = {};
var root = "";
var state = "";
var statusTmp = {};
var statusTick;
var selectedNode = null;
var icons = {"none":"/static/pics/question.png",
            "booted":"/static/pics/gray.png",
            "initialised":"/static/pics/orange.png",
            "configured":"/static/pics/yellow.png",
            "running":"/static/pics/green.png",
            "paused":"/static/pics/blue.png",
            "error":"/static/pics/red.png"
            }

  function statusTable(json, level){
    $.each( json, function(key, item ){
            if (item.hasOwnProperty('children')) {
              $("#statustable").append("<tr><th scope='row'>"+"&emsp;&emsp;".repeat(level)+item.name+"</th><td>"+item.state+"</td><td></td><td></td><td></td></tr>");
              statusTable(item.children, level+1)
        }else{
          $("#statustable").append("<tr><th scope='row'>"+"&emsp;&emsp;".repeat(level)+item.name+"</th><td>"+item.state+"&nbsp; - &nbsp;"+item.process_state+"</td><td>"+item.host+"</td><td>"+item.last_sent_command+"</td><td>"+item.last_ok_command+"</td></tr>");
        }
    })
}
function addId(json){
  $.each( json, function(key,item ){
    if (item.hasOwnProperty('text')) {
      item.id = item.text
    }
    if (item.hasOwnProperty('children')) {
      item.children = addId(item.children)
    }
    })
return json
}
function refreshIcons(states){
  $.each( states, function(key, item ){
    $('#controlTree').jstree("set_icon",'#'+item.text,icons[item.state]);
    if (item.hasOwnProperty('children')) {
      refreshIcons(item.children)
    }
})
}

function populateButtons(){
$( "#stateButtonsDiv" ).empty()
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
  url: "http://"+serverhost+"/nanorcrest/status",
  beforeSend: function(xhr) { 
    xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass")); 
  },
  type: 'GET',
  dataType: "text",
  success: function (d) {
    //d = JSON.stringify(d);
    d = d.replace(/name/g, "text");
    d = JSON.parse(d)
    if (d.hasOwnProperty('children')) {
      d.children = addId(d.children)
    }
    root = d.text
    $('#controlTree').jstree(true).settings.core.data = d;
    $('#controlTree').unbind("refresh.jstree")
    if (d.hasOwnProperty('children')) {
      $('#controlTree').bind("refresh.jstree", function (event, data) {
        refreshIcons(d.children)
      })
    }
    $('#controlTree').jstree(true).refresh();
  },
  error: function(e){
    alert(JSON.stringify(e));
  }
});
}

function refreshTree(tree){
    d = JSON.stringify(tree);
    d = d.replace(/name/g, "text");
    d = JSON.parse(d)
    if (d.hasOwnProperty('children')) {
      d.children = addId(d.children)
    }
    root = d.text
    $('#controlTree').jstree(true).settings.core.data = d;
    $('#controlTree').unbind("refresh.jstree")
    if (d.hasOwnProperty('children')) {
      $('#controlTree').bind("refresh.jstree", function (event, data) {
        $('#controlTree').jstree("set_icon",'#j1_1',icons[d.state]);
        refreshIcons(d.children)
      })
    }
    //refreshIcons(d.children)
    $('#controlTree').jstree(true).refresh();
  }
function sendComm(command,runnumber, runtype){
  clearInterval(statusTick);
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
        //alert(JSON.stringify(d));
        $('#json-renderer').jsonViewer(d,{collapsed: true});
        //getTree()
        statusTick = setInterval(getStatus, 1000, true);
      },
      error: function(e){
      console.log(e)
      }
  });
}
  function getStatus(regCheck=false){
    if (regCheck == true){
      url = "http://"+serverhost+"/nanorcrest/status"
    }else{
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
    }
    $.ajax({
        url: url,
        beforeSend: function(xhr) { 
          xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass")); 
        },
        type: 'GET',
        dataType: "text",
        success: function (d) { 
          d = JSON.parse(d);
          if(d=="I'm busy!"){
            $("#state:text").val('Executing...')
            $(".control").attr("disabled", true);
          }
          else{
            if(d.state!=state){
              $("#state:text").val(d.state)
              state = d.state
              if(url=="http://"+serverhost+"/nanorcrest/status"){
                refreshTree(d)
              }
              populateButtons()
              $("#statustable").empty()
              statusTable({d}, 0)
            }
          }
          
          statusTmp = d;
        },
        error: function(e){
          console.log(e)
        }
    });
  }
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
      statusTick = setInterval(getStatus, 1000, true);
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

          if (d.hasOwnProperty('children')) {
            d.children = addId(d.children)
          }
          root = d.text
          $('#controlTree').jstree({
            'plugins': ['types'],
            'types' : {
                    'default' : {
                    'icon' : '/static/pics/question.png'
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
        getStatus()
        },
        error: function(e){
          alert(JSON.stringify(e));
        }
      });
      $("#selected").text('Selected: '+root)
    })