var idList = {};
var fsmrules = {};
var grafanarules = {};
var ownerFlag = 0;
var mainJson = {};
var log = '';
var node = {};

function exclude(node) {
    $("body").css("cursor", "progress");
    $.ajax({
      method: "POST",
      url: urlForAjax,
      data: { 'node': node, 'command': 'exclude'}
    })
    .done(function( msg ) {
      $("body").css("cursor", "default");
      $('#ajax').trigger('changed.jstree');
    });
}

function include(node) {
    $("body").css("cursor", "progress");
    $.ajax({
      method: "POST",
      url: urlForAjax,
      data: { 'node': node, 'command': 'include'}
    })
    .done(function( msg ) {
      $("body").css("cursor", "default");
      $('#ajax').trigger('changed.jstree');
    });
}

function customMenu(node){
    var items = {
        'item1' : {
            'label' : 'Exclude',
            'action' : function () {
                    exclude(idList[node.id].name)
             }
        },
        'item2' : {
            'label' : 'Include',
            'action' : function () {
            include(idList[node.id].name)
            }
        }
    }
    if ( ownerFlag === 0){
        return {'item1' : {
            'label' : 'Not in control'}}
    }
    if (idList[node.id].included === true) {
        delete items.item2;
    } else if (idList[node.id].included === false) {
        delete items.item1;
    }
    return items;
}

function inconsistencyChecker(){
    $.each(idList, function (key,value){
        if (idList[key].inconsistent === true){
            $( "#"+idList[key].name+"_inconsistent" ).remove()
            $( "#"+idList[key].name+"_inconsistentList" ).remove()
            $( "#"+key+"_anchor" ).append( "<small id='"+idList[key].name+"_inconsistent' style='color:red;'>&nbsp; INCONSISTENT </small>" );
            $("#"+idList[key].name+"_a").append("<small id='"+idList[key].name+"_inconsistentList' style='background-color:#d64161;'> INCONSISTENT &nbsp; </small>");
        } else {
            $( "#"+idList[key].name+"_inconsistent" ).remove()
            $( "#"+idList[key].name+"_inconsistentList" ).remove()
        }
    })
}

function includeChecker(){
    $.each(idList, function (key,value){
         $("#"+key+"_Checkbox").off("click");
        if ($("#"+key).length){
            if ($("#"+key+"_Checkbox").length === 0){
                //$("#"+key).append('<input type="checkbox" id="'+key+'_Checkbox" class="regular-checkbox group1" /><label class="" for="'+key+'_Checkbox"></label></input>' )
                 $('<input type="checkbox" id="'+key+'_Checkbox" class="regular-checkbox group1"><label class="" for="'+key+'_Checkbox"></label>' ).insertAfter( "#"+key+"_anchor" )
            }
        }
        if (idList[key].included === false){
            $("#"+key+"_anchor").css("background-color", "grey");
            $("#"+key+"_Checkbox").prop( "checked", false );
            $("#"+key+"_Checkbox").click(function(){
			       include(value.name)
		    });
            $( "#"+key+"_include" ).remove()
            $("#"+idList[key].name+"_a").append("<span id='"+key+"_include' class='excludedLab'><i class=\"fa fa-exclamation-triangle\" aria-hidden=\"true\"></i>\n<strong class=''>excluded </strong><i class=\"fa fa-exclamation-triangle\" aria-hidden=\"true\"></i></span>\n");
        } else {
            $("#"+key+"_Checkbox").prop( "checked", true );
            $("#"+key+"_Checkbox").click(function(){
			       exclude(value.name)
		    });
            $("#"+key+"_anchor").css("background-color", "");
            $( "#"+key+"_include" ).remove()
        }
    })
}
function redrawLock(){
         if (ownerFlag == 0) {
            $(".control").prop('disabled', true);
            $("input.group1").prop("disabled", true);
            $("#lock").html('<i class="fas fa-unlock fa-fw"></i>');
            $("#LockStatusText").html('Monitoring GUI');
            $("#LockStatusText").css("background-color", "lightyellow");
        } else if (ownerFlag == 1) {
            $(".control").prop('disabled', false);
            $("input.group1").prop("disabled", false);
            $("#lock").html('<i class="fas fa-lock fa-fw"></i>');
            $("#LockStatusText").html('Control GUI');
            $("#LockStatusText").css("background-color", "lightgreen");
        }
        refreshIcons()
    }

function sendComm(id, node, command) {
    $("#buttonup").prop('disabled', true);
    $("#buttondown").prop('disabled', true);
    $("#state:text").val('Executing...')
    $("body").css("cursor", "progress");
    $.ajax({
      method: "POST",
      url: urlForAjax,
      //contentType: 'application/json;charset=UTF-8',
      data: { 'node': node, 'command': command}
    })
    .done(function( msg ) {
      refreshIcons()
      redrawLock()
      $("body").css("cursor", "default");
      $('#ajax').trigger('changed.jstree');
    });
}

function childrenTree(json, lId){
    $.each( json, function(key, item ){
        $(lId).append("<li id="+item.text+"_a class='childItemList w-100'><span style='width: 10px;'><img style='width: 20px;' src="+returnIcon(idList[findIdByName(item.text)].state)+">&nbsp;</img></span>"+item.text+" - "+idList[findIdByName(item.text)].state+"&nbsp;</li>");
            if (item.hasOwnProperty('children')) {
            $(lId).append("<ul id="+item.text+"_list>");
            childrenTree(item.children, "#"+item.text+"_list")
            $(lId).append("</ul>");
        }
    })
}

function getObjects(obj, key, val) {
    var objects = [];
    for (var i in obj) {
        if (!obj.hasOwnProperty(i)) continue;
        if (typeof obj[i] == 'object') {
            objects = objects.concat(getObjects(obj[i], key, val));
        } else if (i == key && obj[key] == val) {
            objects.push(obj);
        }
    }
    return objects;
}
function updateState(){
        $.ajax({
          method: "POST",
          url: urlForStates,
          //contentType: 'application/json;charset=UTF-8',
          data: { 'update': 1}
        })
        .done(function( msg ) {
          refreshIcons()
          redrawLock()
          $("body").css("cursor", "default");
          $('#ajax').trigger('changed.jstree');
        });
        $.getJSON(urlForStates,function(d){
            if (d['whoLocked'] === usr){
                ownerFlag = 1
            } else if (d['whoLocked'] !== usr) {
                ownerFlag = 0
            }
            $.each(idList, function (key,value){
                 idList[key].state = d[value['name']][0]
                 idList[key].inconsistent = d[value['name']][1]
                 idList[key].included = d[value['name']][2]
            })
        })
        .done(function() {
            $('#ajax').trigger('changed.jstree');
            refreshIcons()
            redrawLock()
            inconsistencyChecker()
            //includeChecker()
        })
       };
function findIdByName(val){
            var ret = ''
            $.each( idList, function( key, value ) {
              if(value.name === val){
                    ret = key
              }
            });
            return ret
        }
function updateConfigs(){
        $("#configMenu").empty()
        $("#configMenuStart").empty()
        $("#filters2").empty()
        $("#filters").empty()
        $("#filters").append("<li><label><input type='checkbox' id='filterinfo' class='filterchng' checked> INFO</label> ");
        $("#filters").append("<label><input type='checkbox' id='filterwarning' class='filterchng'> WARNING</label> ");
        $("#filters").append("<label><input type='checkbox' id='filtererror' class='filterchng'> ERROR</label> ");
        $("#filters").append("<label><input type='checkbox' id='filterdebug' class='filterchng'> DEBUG</label> ");
        $("#filters2").append("<label><input type='checkbox' id='c_general' class='filterchng' checked> general</label></li>");
        $.getJSON(urlForConfigs,function(d){
            $.each(d, function (key,file){
                 $("#configMenu").append("<button id='"+file.replace(".", "")+"' class=\"green button w-100 mb-1\">"+file+"</button>");
                 $("#configMenuStart").append("<button id='m_"+file.replace(".", "")+"' class=\"green button w-100 mb-1\">"+file+"</button>");
                 $("#filters2").append("<li><label><input type='checkbox' value='"+file.replace(".", "")+"' id='c_"+file.replace(".", "")+"' class='filterchng'>"+file+"</label></li>");
                 $("#m_"+file.replace(".", "")).on('click', function(){
                    $("#"+file.replace(".", "")).click();
                 });
                 $("#"+file.replace(".", "")).on('click', function(){
                   $.ajax({
                      method: "POST",
                      url: urlForConfigs,
                      //contentType: 'application/json;charset=UTF-8',
                      data: { 'configFile': file}
                    })
                    .done(function( res ) {
                       window.location.reload();
                    });


                 });
            })
            $("#c_"+currConfigFile.replace(".", "")).prop("checked", true);
            $(".filterchng").change(function() {
                applyFilters()
            });
            // $("#configMenu").append('<div class="dropdown-divider"></div><button id="configUploadButton" class="darkb button w-100">Upload new configuration</button>');
            // $("#configMenu").append('<form id="upload-file" method="post" enctype="multipart/form-data"><input type="file" id="configurationupload" style="display:none"/></form> ');
            // $('#configUploadButton').click(function(){ $('#configurationupload').trigger('click'); });
            // $("#configMenu").append('<div class="dropdown-divider"></div><button id="uploadButton" class="darkb button w-100">Upload new tree/FSM/deviceconfig</button>');
            // $("#configMenu").append('<input type="file" id="upload" style="display:none"/> ');
            // $('#uploadButton').click(function(){ $('#upload').trigger('click'); });
            // $("#configurationupload").change(function(){
            //         var file = $('#configurationupload').prop('files');
            //         uploadFile(file, urlForuploadMainConfigurationFile)
            // });
            // $("#upload").change(function(){
            //         var file = $('#upload').prop('files');
            //         uploadFile(file, urlForuploadCfgFile)
            // });
        })


       };

function applyFilters(){
    filterArray=[]
    uncheckedFilters=[]
    $(".filterchng").each(function(){
        var $this = $(this);
        if($this.is(":checked")){
            filterArray.push($this.attr("id"));
        }else{
            uncheckedFilters.push($this.attr("id"));
        }
    });
    sessionStorage.setItem("checked", JSON.stringify(filterArray));
    sessionStorage.setItem("unchecked", JSON.stringify(uncheckedFilters));
    $("#logList").empty();
    $.getJSON(urlForLog,function(d){
                arr = d.split('\n')
                $.each(arr, function (key, item){
                    add = 1
                    if (item){
                        var matches = item.match(/\[(.*?)\]/);
                        if(item.indexOf("INFO") != -1){
                            if((document.getElementById('filterinfo').checked) && ($.inArray("c_"+matches[1].replace(".", ""), filterArray) !== -1)) {
                                $("#logList").prepend("<li class='bg-info'>"+(item.replace(/[<>]/g, ''))+"</li>");
                            }
                        }else if(item.indexOf("WARNING") != -1){
                            if((document.getElementById('filterwarning').checked) && ($.inArray("c_"+matches[1].replace(".", ""), filterArray) !== -1)) {
                                $("#logList").prepend("<li class='bg-warning'>"+(item.replace(/[<>]/g, ''))+"</li>");
                            }
                        }else if(item.indexOf("ERROR") != -1){
                           if((document.getElementById('filtererror').checked) && ($.inArray("c_"+matches[1].replace(".", ""), filterArray) !== -1)) {
                                $("#logList").prepend("<li class='bg-danger'>"+(item.replace(/[<>]/g, ''))+"</li>");
                            }
                        }else if(item.indexOf("DEBUG") != -1){
                            if((document.getElementById('filterdebug').checked) && ($.inArray("c_"+matches[1].replace(".", ""), filterArray) !== -1)) {
                                $("#logList").prepend("<li class='bg-secondary'>"+(item.replace(/[<>]/g, ''))+"</li>");
                            }
                        }else{
                            if((document.getElementById('filterdebug').checked) && ($.inArray("c_"+matches[1].replace(".", ""), filterArray) !== -1)) {
                                $("#logList").prepend("<li class='bg-secondary'>"+(item.replace(/[<>]/g, ''))+"</li>");
                            }
                        }
                   }
                })
            })
}

function uploadFile(file, url){
    var data = new FormData();
    data.append('file', file[0]);
        $.ajax({
            type: 'POST',
            url: url,
            data: data,
            contentType: false,
            cache: false,
            processData: false,
            success: function(r) {
                alert(r);
            },
        });
        updateConfigs()
}
function getLog(){
        $.getJSON(urlForLog,function(d){
            arr = d.split('\n')
            $.each(arr, function (key, item){
                color = "white"
                if(item.indexOf("INFO") != -1){ color = "bg-info" }
                else if(item.indexOf("WARNING") != -1){ color = "bg-warning" }
                else if(item.indexOf("ERROR") != -1){ color = "bg-danger" }
                 $("#logList").prepend("<li class='"+color+"'>"+item+"</li>");
            })
        }).done(function() {
            applyFilters()
            var retrievedData = JSON.parse(sessionStorage.getItem("checked"));
        })
       };


function updateFsm(){
        $.getJSON(urlForFsm,function(d){
            fsmrules = d
        })
       };

function updateGrafana(){
        $.getJSON(urlForGrafana,function(d){
            grafanarules = d
        })
       };
function refreshIcons(){
    $.each(idList, function (key,value){
        $('#ajax').jstree("set_icon",'#'+key,returnIcon(idList[key].state));
    })
}




$('#ajax').on('open_node.jstree', function () {
    inconsistencyChecker()
    includeChecker()
    redrawLock()
    refreshIcons()

})

$('#ajax').on('changed.jstree', function () {
            selId= $("#ajax").jstree("get_selected",true)[0].id
            selState = idList[$("#ajax").jstree("get_selected",true)[0].id].state
            $(".control").off("click");
            $( "#stateButtonsDiv" ).empty()
            var statearr = selState;
            if(typeof(selState)==="string")
            {
                statearr=[]
                statearr[0] = selState
            }
            var values = []
            $.each( statearr, function(key, value){
                    $.each( fsmrules[value], function(key, value ){
                        if(!(values.includes(value)))
                        {
                            values.push(value)
                        }
                    })
                })
                $.each(values, function(key, value){
                    $("#stateButtonsDiv").append("<button id='"+value+"_button' class='green button control' style='margin:5px;'>"+value.toUpperCase()+"</button> &nbsp &nbsp");
                    $("#"+value+"_button").on('click', function(){
                        var id = $("#ajax").jstree("get_selected",true)[0].id;
                        var node = $("#ajax").jstree("get_selected",true)[0].text;
                        sendComm(id, node, value);
                    });
                })

            redrawLock()
            $("#state:text").val(idList[$("#ajax").jstree("get_selected",true)[0].id].state);
            $("#statelog").empty();
            $("#childlist").empty();
            selText = $("#ajax").jstree("get_selected",true)[0].text
            try {
                partJson=getObjects(mainJson, 'text', selText)[0].children
            }
            catch(err) {
                partJson=''
            }
            childrenTree(partJson, "#childlist")
            includeChecker()
            inconsistencyChecker()
            oldNode = node
            node = $("#ajax").jstree("get_selected",true);
            sessionStorage.setItem("selectednode", node[0].id);
            var jst = $('#ajax').jstree('get_json')
            sessionStorage.setItem("jst", JSON.stringify(jst));
            sessionStorage.setItem("selectednode", node[0].id);
            var selectednode = sessionStorage.getItem("selectednode");
            $("#name").html("Selected node: " + node[0].text + "&nbsp; &nbsp; <button id='kibana' class='text-center' style='margin:5px;'>Node log</button>");
            if (oldNode[0] !== node[0]){
                selText = $("#ajax").jstree("get_selected",true)[0].text
                $( "#iframesector").empty()
                if (selText in grafanarules){
                    if ("kibana" in grafanarules[selText]){
                            console.log(grafanarules[selText]["kibana"])
                            $("#kibana").unbind();
                            $("#kibana").bind("click", function() {
                                    window.open(grafanarules[selText]["kibana"]);
                            });
                    }
                    if ("grafana" in grafanarules[selText]){
                        $.each( grafanarules[selText]["grafana"], function(key, value ){
                           $("#iframesector").append("<div class='col-sm-12 col-md-6 col-lg-4'><div class='embed-responsive embed-responsive-4by3'><iframe class='embed-responsive-item' src='"+value+"' style='border:3px;'></iframe></div></div>");
                        })
                    }
                }
            }

            if($("#"+node[0].id).hasClass("jstree-node")) {
                $('#detailPage').show();
                $('#lock').prop('disabled', false);
                $('#detailPage3').hide();
            } else {
                $('#detailPage').hide();
                $('#lock').prop('disabled', true);
                $('#detailPage3').hide();
            }

})

	$('#ajax').on('loaded.jstree', function () {
	    $('#lock').prop('disabled', false);
	    var jsonNodes = $('#ajax').jstree('get_json', null, { 'flat': true });
        $.each(jsonNodes, function (i, val) {
            idList[val.id] = {'name':val.text, state: 'not_added', inconsistent: false, included: true};
         });
         var selectednode = sessionStorage.getItem("selectednode");
         var jst = JSON.parse(sessionStorage.getItem("jst"));
         $('#ajax').jstree(jst);
         if(selectednode == null){
		    $('#ajax').jstree('select_node', '#j1_1', 'True');
		 }else{
		    $('#ajax').jstree('select_node', '#'+selectednode, 'True');

		 }
		 includeChecker()
		 updateState()
		 applyFilters()
         //setInterval( updateState, 1000);
		});

	$(window).resize(function () {
		var h = Math.max($(window).height() - 0, 420);
		 // $('#container, #data, #tree').height(h).filter('.default').css('height', h + 'px');
		 // h=h-200;
		 // $('#data .content').height(h).filter('.default').css('height', h + 'px');
	}).resize();
    $(document).ready(function() {
    var jst = sessionStorage.getItem("jst");
        $.getJSON(urlTreeJson,function(d){
            $('#ajax').jstree({
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
                mainJson = d
            })
           //}

        $('#lock').prop('disabled', true);
        updateFsm()
        updateConfigs()
        updateGrafana()
        getLog()
        var checked = JSON.parse(sessionStorage.getItem("checked"));
        $.each(checked, function (key, item){
                $( "#"+item ).prop( "checked", true );
            })
        var unchecked = JSON.parse(sessionStorage.getItem("unchecked"));
        $.each(checked, function (item){
                $( "#"+item ).prop( "checked", false );
            })
        var log = sessionStorage.getItem("log");
        if(log == "closed"){
            $('#logArea').height("0px");
            $("#logShow").html('Show');
        } else {
            $('#logArea').height("450px");
            $("#logShow").html('Hide');
        }
        applyFilters()
         var socket = io();
         socket.on('connect', function() {
            socket.emit('message', {data: 'Im connected!'});
          });
          socket.on('logChng', function(d) {
                add = 1;
                if(d.indexOf("INFO") != -1){
                    if (($('input[name=r_logging]:checked').val() === 'warning')||($('input[name=r_logging]:checked').val()=== 'error')||($('input[name=r_logging]:checked').val()=== 'debug')){add = 0;}
                    color = "bg-info"
                }else if(d.indexOf("WARNING") != -1){
                    if (($('input[name=r_logging]:checked').val() === 'error')||($('input[name=r_logging]:checked').val()=== 'debug')){add = 0;}
                    color = "bg-warning"
                }else if(d.indexOf("ERROR") != -1){
                    if ($('input[name=r_logging]:checked').val() === 'debug'){add = 0;}
                    color = "bg-danger"
                }else if(d.indexOf("DEBUG") != -1){
                    color = "bg-secondary"
                }
                if(add = 1){
                    $("#logList").prepend("<li class='"+color+"'>"+(d.replace(/[<>]/g, ''))+"</li>");(d.replace(/[<>]/g, ''))
                }
           })
          socket.on('message', function(msg) {
            console.log(msg)
          });
          socket.on('stsChng'+currConfigFile, function(d) {
            $.each(idList, function (key,value){
                 idList[key].state = d[value['name']][0]
                 idList[key].inconsistent = d[value['name']][1]
                 idList[key].included = d[value['name']][2]
            })
            inconsistencyChecker()
            //includeChecker()
            refreshIcons()
            $("body").css("cursor", "default");
            redrawLock();
            $('#ajax').trigger('changed.jstree');
          });
          socket.on('interlockChng', function(d) {
          if (d === undefined){
            $("#wholocked").html('None');
          }else{
            $("#wholocked").html(d);
          }

            if (d === usr){
                ownerFlag = 1
            } else {
                ownerFlag = 0
            }
            redrawLock()
          });


	});


 $('#logShow').click(function(){
        if($('#logArea').css("height") == "0px") {
          sessionStorage.setItem("log", "open");
          $('#logArea').animate({height: "370px"}, 1000);
          $("#logShow").html('Hide');
        } else {
          $('#logArea').animate({height: "0px"}, 1000);
          sessionStorage.setItem("log", "closed");
          $("#logShow").html('Show');
        }
        return false;
    });


$('#lock').click(function(){
	$.ajax({
		method: "POST",
		url: urlForInterlock,
		data: { value: 'd'}
	})
	.done(function( msg ) {
	    alert( msg );
		if (msg == "Control has been released") {
           ownerFlag = 0;
        } else if (msg == "Control has been taken") {
           ownerFlag = 1;
        }
        redrawLock();
	});
});

