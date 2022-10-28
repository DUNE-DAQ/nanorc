var commands = {};
var root = "";
var state = "";
var previous_data = "";
var statusTmp = {};
var statusTick;
// var selectedNode = null;
var alertedOnDead = []
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


function getTree(){
    $.ajax({
        url: "http://"+serverhost+"/nanorcrest/status",
        beforeSend: function(xhr) {
            xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass"));
        },
        type: 'GET',
        dataType: "text",
        success: function (d) {
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
            $('#controlTree').jstree(true).open_all();
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
function sendComm(command){
    invalidVals = ""
    arr = $("#modalBody :input");
    var dataload = {"command":command}
    r = $.each(arr, function( index, value ) {
        if(!value.checkValidity()){
            invalidVals = invalidVals + value.id + ", "
        }
        if (value.value != "") {
            dataload[value.id]=value.value
            if (value.type == "checkbox")
            {
                dataload[value.id]=value.checked
            }
        }
    })
    if(invalidVals!=""){
        alert("Provide correct input for "+invalidVals.slice(0,-2))
        return
    }
    $('#argumentsModal').modal('toggle');
    clearInterval(statusTick);
    $("#state:text").val('Executing...')
    $(".control").attr("disabled", true);

    $.ajax({
        url: "http://"+serverhost+"/nanorcrest/command",
        beforeSend: function(xhr) {
            xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass"));
        },
        type: 'POST',
        data: dataload,
        success: function (d) {
            //alert(JSON.stringify(d));
            data = d
            $('#response-render').empty()
            if (data.hasOwnProperty('command')) {
                if (data['return_code'] != 0) {
                    $('#response-render').append('<h4>Last command sent: '+data['command']['command']+' <font color:red>Unsuccessful!</font></h4>')
                }else{
                    $('#response-render').append("<h4>Last command sent: "+data['command']['command']+"</h4>")
                }
                if (data['command'].length>1) {
                    $('#response-render').append("Arguments:")
                    $.each(data, function(key, value) {
                        if (key!="command") {
                            $('#response-render').append(key+": "+value)
                        }
                    });
                }
            } else {
                $('#response-render').append("<h4>Last command sent:</h4>")
            }
            if (data.hasOwnProperty('logs')) {
                var log_string = '<div class="accordion" id="accordionLogs" role="tablist" aria-multiselectable="true">' +
                    '<div class="card">' +
                    '<div class="card-header" id="headingOne">' +
                    '<a data-toggle="collapse" data-target="#collapseOne" aria-expanded="true" aria-controls="collapseOne">' +
                    '<h6 class="mb-0">'+
                    'Logs' +
                    '<i class="fas fa-angle-down rotate-icon"></i>'+
                    '</h6>' +
                    '</a>' +
                    '</h2>' +
                    '</div>' +
                    '<div id="collapseOne" class="collapse" aria-labelledby="headingOne" data-parent="#accordionLogs">' +
                    '<div class="card-body">' +
                    '<pre>'+
                    data['logs'] +
                    '</pre>'+
                    '</div>'+
                    '</div>'+
                    '</div>'

                $('#response-render').append(log_string)

                // $('#response-render').append('<div id="collapse1" class="panel-collapse collapse">')
                // $('#response-render').append('<div class="panel-body">'+data['logs']+ '</div>')
                // $('#response-render').append('</div>')
                // $('#response-render').append('</div>')
                // $('#response-render').append('</div>')
            }
            //getTree()
            $(".control").attr("disabled", false);
            $("#state:text").val(state)
            getStatus()
            statusTick = setInterval(getStatus, 1000, true);
        },
        error: function(e){
            console.log(e)
        }
    });
}
function fetchCommands(){
    $.ajax({
        url: "http://"+serverhost+"/nanorcrest/command",
        beforeSend: function(xhr) {
            xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass"));
        },
        type: 'GET',
        dataType: "text",
        success: function (d) {
            d = JSON.parse(d)
            commands = d;
            $( "#stateButtonsDiv" ).empty()
            $.each(d, function( index, value ) {
                $("#stateButtonsDiv").append("<button id='"+index+"' class='green button control' data-toggle='modal' data-target='#argumentsModal' style='margin:5px;'>"+index+"</button> &nbsp &nbsp");
            });
            $(".control").click(function() {
                populateArgs($(this).attr("id"));
            });
        },
        error: function(e){
            console.log(e)
        }
    });

}
function populateArgs(command){
    $("#ModalLabel").text("Arguments for "+command+":");
    $("#executeBtn").text("Execute "+command+" command");
    $("#modalBody").empty()
    $("#modalBody").append("<form id='argForm' class='needs-validation' novalidate>");
    $.each(commands[command], function( index, value ) {
        $.each(value, function( i, v ) {
            var clss = v.type
            var defaul = ""
            var apendix = ""
            if(v.default != null){
                defaul = v.default
            }
            if(v.required){
                apendix = apendix + "required"
                clss += " required"
            }
            $("#modalBody").append("<h6>"+i+"</h6>");
            if (v.type == "BOOL"){
                $("#modalBody").append('<input type="checkbox" id="'+i+'" class="'+clss+'"><br>');
                if (defaul == true){$( "#"+i ).prop( "checked", true );}
            }else if (v.type == "INT"){
                $("#modalBody").append('<input type="number" value="'+defaul+'" id="'+i+'" class="form-control '+clss+'" '+apendix+'>');
            }else if(/choice/i.test(v.type)){
                choices = (v.type).match(/\[(.*?)\]/);
                choices = choices[1].split(',');
                $("#modalBody").append('<select id="'+i+'"></select><br>');
                $.each(choices, function( j, w ) {
                    w = w.replace(/'/g, "");
                    $("#"+i).append('<option value="'+w+'">'+w+'</option>');
                })
            }else{
                $("#modalBody").append('<input type="text" value="'+defaul+'" id="'+i+'" class="form-control '+clss+'" '+apendix+'>');
            }
            $("#modalBody").append("<small><i>"+clss+"</i></small>");
        });
    });
    $("#modalBody").append("</form>");
    $("#executeBtn").unbind();
    $("#executeBtn").click(function() {
        sendComm(command);
    });
}

function alertOnDead(data, root_path){
    if (data.hasOwnProperty('children')) {
        $.each(data['children'], function (index, child){
            alertOnDead(child, root_path+data['name']+'/')
        });
    }else if (data.hasOwnProperty('process_state')) {
        var name = data['name']

        if (data['process_state'].includes('dead')) {
            if (!alertedOnDead.includes(name)){
                alert(root_path+name+' died :(')
                alertedOnDead.push(name)
            }
        }
    }
}


function getStatus(regCheck=false){
    if (regCheck == true){
        url = "http://"+serverhost+"/nanorcrest/status"
    }else{
        // if(selectedNode==null){
            url = "http://"+serverhost+"/nanorcrest/status"
        // }else{
        //     // if(selectedNode.text==root){
        //     url = "http://"+serverhost+"/nanorcrest/status"
        //     // }else{
        //     //     selText= selectedNode
        //     //     path=$('#controlTree').jstree(true).get_path(selText,".")
        //     //     path = path.replace(root+".", "");
        //     //     url = "http://"+serverhost+"/nanorcrest/node/"+path
        //     // }
        // }
    }
    $.ajax({
        url: url,
        beforeSend: function(xhr) {
            xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass"));
        },
        type: 'GET',
        dataType: "text",
        success: function (d) {
            data = JSON.parse(d);
            if(data=="I'm busy!"){
                // console.log("busy answer")
                $("#state:text").val('Executing...')
                $(".control").attr("disabled", true);
            }else{
                if(d != previous_data){
                    // console.log("new state")
                    $("#state:text").val(data.state)
                    previous_data = d
                    if(url=="http://"+serverhost+"/nanorcrest/status" && state!=data.state){
                        refreshTree(data)
                    }
                    state = data.state
                    alertOnDead(data, "/")
                    fetchCommands()
                    $("#statustable").empty()
                    statusTable({data}, 0)
                }// else{
                // console.log("nothing changed")
                // }
            }

            statusTmp = d;
        },
        error: function(e){
            console.log(e)
        }
    });
}


// $('#controlTree').on('changed.jstree', function () {
//     // selected
//     Node = $("#controlTree").jstree("get_selected",true)[0]
//     getStatus()
//     // if(selectedNode != null){
//     //     $("#selected").text('Selected: '+selectedNode.text)
//     // }else{
//     // $("#selected").text('Selected: '+root)
//     // }

// })
$(window).resize(function () {
    var h = Math.max($(window).height() - 0, 420);
    // $('#container, #data, #tree').height(h).filter('.default').css('height', h + 'px');
    // h=h-200;
    // $('#data .content').height(h).filter('.default').css('height', h + 'px');
}).resize();
$(document).ready(function() {
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
    // $("#selected").text('Selected: '+root)
})
