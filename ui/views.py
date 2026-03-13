from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    return render(request, 'ui/index.html')


@login_required
def sql_editor(request):
    return render(request, 'ui/sql_editor.html')
