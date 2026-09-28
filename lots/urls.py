from django.urls import path
from .views import SpreadsheetParseAPIView

urlpatterns = [
    path('api/lots/parse/', SpreadsheetParseAPIView.as_view(), name='lot-spreadsheet-parse'),
]
