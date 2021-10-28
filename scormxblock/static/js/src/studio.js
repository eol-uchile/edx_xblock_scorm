function ScormStudioXBlock(runtime, element, settings) {

  var handlerUrl = runtime.handlerUrl(element, 'studio_submit');
  var handlerUrlTaskStatus = runtime.handlerUrl(element, 'studio_submit_status');
  var handlerUrlSaveTaskId = runtime.handlerUrl(element, 'save_task_id');
  var status_runtime = 'save';
  function ScormCheckStatus(){
    $.ajax({
        url: handlerUrlTaskStatus,
        dataType: 'json',
        cache: false,
        contentType: false,
        processData: false,
        type: "POST",
        success: function(data) {
            if (status_runtime == 'save'){
                if (data["task_state"] == 'running'){
                    setTimeout(ScormCheckStatus, 5000);
                }
                else{
                    if(data['task_state'] == 'complete'){
                        return ScormUpdateXblock();
                    }
                    else{
                        return ScormTaskError(data['task_state']);
                    }
                }
            }
            else{
                status_runtime = 'error';
                runtime.notify("error", {
                    "message": "La subida del archivo fue cancelada.",
                    "title": "Scorm component save error"
                });
            }
            
        },
        error: function() {
            return ScormTaskError('error');
        }
    })
}
function ScormTaskError(status){
    if(status == 'error'){
        var error = 'Error al subir el archivo, contáctese con mesa de ayuda.'
    }
    else{
        var error = 'Error al procesar el archivo, contáctese con mesa de ayuda.'
    }
    status_runtime = 'error';
    runtime.notify("error", {
        "message": error,
        "title": "Scorm component save error"
    });
}
function ScormUpdateXblock(){
    var form_data = new FormData();
    form_data.append('task_step', 'complete');
    $.ajax({
        url: handlerUrl,
        dataType: 'json',
        cache: false,
        contentType: false,
        processData: false,
        data: form_data,
        type: "POST",
        success: function(response) {
            if (response.errors.length > 0) {
                response.errors.forEach(function(error) {
                    status_runtime = 'error';
                    runtime.notify("error", {
                        "message": error,
                        "title": "Scorm component save error"
                    });
                });
            } else {
                status_runtime = 'end';
                runtime.notify('save', {
                    state: 'end'
                });
            }
        }
    });
    
}
function ScormTaskCreate(data){
    var form_data = new FormData();
    form_data.append('extract_folder_path', data.extract_folder_path);
    form_data.append('package_path', data.package_path);
    form_data.append('course_id', settings.course_id);
    form_data.append('block_id', settings.block_id);
    form_data.append('token', settings.token);
    $.ajax({
        url: settings.url_task,
        dataType: 'json',
        cache: false,
        contentType: false,
        processData: false,
        data: form_data,
        type: "POST",
        xhrFields: {
            withCredentials: true
        },
        success: function(data) {
            var form_data2 = new FormData();
            form_data2.append('task_id', data.task_id);
            $.ajax({
                url: handlerUrlSaveTaskId,
                dataType: 'json',
                cache: false,
                contentType: false,
                processData: false,
                data: form_data2,
                type: "POST",
                success: function(data) {
                    ScormCheckStatus()
                },
                error: function() {
                    return ScormTaskError('error');
                }
            })
        },
        error: function() {
            return ScormTaskError('error');
        }
    })
}
  $(element).find('.save-button').bind('click', function() {
      var form_data = new FormData();
      var file_data = $(element).find('#scorm_file').prop('files')[0];
      var display_name = $(element).find('input[name=display_name]').val();
      var has_score = $(element).find('select[name=has_score]').val();
      var weight = $(element).find('input[name=weight]').val();
      var width = $(element).find('input[name=width]').val();
      var height = $(element).find('input[name=height]').val();

      form_data.append('file', file_data);
      form_data.append('display_name', display_name);
      form_data.append('has_score', has_score);
      form_data.append('weight', weight);
      form_data.append('width', width);
      form_data.append('height', height);
      form_data.append('task_step', 'initial');
      form_data.append('task_token', settings.token);
      runtime.notify('save', {
          state: 'start'
      });
      status_runtime = 'save';
      $.ajax({
          url: handlerUrl,
          dataType: 'json',
          cache: false,
          contentType: false,
          processData: false,
          data: form_data,
          type: "POST",
          xhrFields: {
              withCredentials: true
            },
          success: function(response) {
              if (response.errors.length > 0) {
                  response.errors.forEach(function(error) {
                      status_runtime = 'error';
                      runtime.notify("error", {
                          "message": error,
                          "title": "Scorm component save error"
                      });
                  });
              } else {
                  ScormTaskCreate(response.data_task)
              }
          }
      });

  });

  $(element).find('.cancel-button').bind('click', function() {
      status_runtime = 'error';
      runtime.notify('cancel', {});
  });

  $(function () {
    var show_or_hide_warning = () => {
        let has_score = $(element).find('select[name=has_score]').val();
        let $warning = $(element).find('.setting-has_score')
        has_score == 'True' ? $warning.show() : $warning.hide();
    }
    $(element).find('select[name=has_score]').change(()=> {
        show_or_hide_warning();
    });
    show_or_hide_warning(); // on init
  });

}