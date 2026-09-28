from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
import json

from .importer import parse_spreadsheet

class SpreadsheetParseAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        
        if not file_obj:
            return Response(
                {"error": "No file uploaded. Please provide a 'file' in the form data."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        filename = file_obj.name.lower()
        if not (filename.endswith('.csv') or filename.endswith('.xlsx') or filename.endswith('.xls')):
            return Response(
                {"error": "Invalid file format. Only .csv, .xls, and .xlsx files are supported."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        mapping_str = request.data.get('mapping')
        mapping = None
        if mapping_str:
            try:
                mapping = json.loads(mapping_str)
            except json.JSONDecodeError:
                return Response(
                    {"error": "Malformed JSON in 'mapping' parameter."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        try:
            # Parse the spreadsheet
            result = parse_spreadsheet(file_obj, manual_mapping=mapping)
            return Response(result, status=status.HTTP_200_OK)
            
        except ValueError as e:
            # Catch known parsing errors or validation errors
            return Response(
                {"error": str(e)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        except Exception as e:
            # Catch any other unexpected errors
            return Response(
                {"error": f"Failed to parse spreadsheet: {str(e)}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
