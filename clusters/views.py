import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from common.config import QUERY_DEFAULT_ACCOUNT, QUERY_DEFAULT_PASSWORD
from .query_arch import query_nodes_in_cluster

logger = logging.getLogger('dbs')


class QueryArchView(APIView):
    """查询 MySQL 集群拓扑（GET），固定使用 dbs_admin 账号"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ip = request.GET.get('ip', '')
        try:
            port = int(request.GET.get('port', 0))
        except (TypeError, ValueError):
            port = 0

        if not ip or not port:
            return Response(
                {'error': True, 'message': 'ip、port 不能为空', 'nodes': []},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            nodes = query_nodes_in_cluster(ip, port, QUERY_DEFAULT_ACCOUNT, QUERY_DEFAULT_PASSWORD)
            return Response({'error': False, 'message': '', 'nodes': nodes})
        except Exception as exc:
            logger.exception('query_arch 失败 ip=%s', ip)
            return Response(
                {'error': True, 'message': str(exc), 'nodes': []},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
