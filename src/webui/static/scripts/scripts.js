
    function getTree(){
       /*  $.get({
            url: "host.docker.internal:5001/nanorcrest/tree",
            beforeSend: function(xhr) { 
              xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass")); 
            },
            //type: 'GET',
            crossOrigin: true,
            success: function (data) {
              alert(JSON.stringify(data));
            },
            error: function(e){
              alert(JSON.stringify(e));
            }
        });} */
       }
        function sendComm(){
          console.log('sending')
           $.ajax({
               url: "http://localhost:5001/nanorcrest/status",
               beforeSend: function(xhr) { 
                 xhr.setRequestHeader("Authorization", "Basic " + btoa("fooUsr:barPass")); 
               },
               type: 'GET',
               crossOrigin: true,
               crossDomain: true,
               dataType: "text",
               contentType:'text/plain',
               cors: true ,
               //dataType: "jsonp",
               //data: "command=BOOT",
               success: function (d) {
                 alert(JSON.stringify(d));
                 console.log(d)
               },
               error: function(e){
                console.log(e)
               }
           });}

  $('#but').click(function(){
    sendComm()
  });
  $('#ajax').on('changed.jstree', function () {
    selText= $("#ajax").jstree("get_selected",true)[0].text
    console.log(selText)
  })
	$(window).resize(function () {
		var h = Math.max($(window).height() - 0, 420);
		 // $('#container, #data, #tree').height(h).filter('.default').css('height', h + 'px');
		 // h=h-200;
		 // $('#data .content').height(h).filter('.default').css('height', h + 'px');
	}).resize();
    $(document).ready(function() {
        $.getJSON(urlTree,function(d){
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
            })