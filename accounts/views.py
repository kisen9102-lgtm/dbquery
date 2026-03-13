import json
import logging

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from .models import GroupMembership, InstanceGroup, UserProfile, ROLE_ADMIN, ROLE_QUERY

logger = logging.getLogger('dbs')


# ── 权限辅助 ──────────────────────────────────────────────────────────────────

def _is_admin_or_root(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return profile and profile.role == ROLE_ADMIN


def _get_profile(user):
    try:
        return user.profile
    except UserProfile.DoesNotExist:
        return None


# ── 登录 / 注册 / 登出（模板视图）────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('/')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(request.POST.get('next', '/'))
        error = '用户名或密码错误'
    return render(request, 'accounts/login.html', {'error': error, 'next': request.GET.get('next', '/')})


def logout_view(request):
    logout(request)
    return redirect('/accounts/login/')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('/')
    error = None
    success = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        if not username or not password:
            error = '用户名和密码不能为空'
        elif password != password2:
            error = '两次密码不一致'
        elif len(password) < 6:
            error = '密码长度至少 6 位'
        elif User.objects.filter(username=username).exists():
            error = '该用户名已被注册'
        else:
            user = User.objects.create_user(username=username, password=password)
            UserProfile.objects.create(user=user, role=ROLE_QUERY)
            success = '注册成功，请登录'
    return render(request, 'accounts/register.html', {'error': error, 'success': success})


# ── API: 当前用户信息 ─────────────────────────────────────────────────────────

class MeView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        profile = _get_profile(user)
        role = 'root' if user.is_superuser else (profile.role if profile else ROLE_QUERY)
        return Response({
            'id': user.id,
            'username': user.username,
            'role': role,
            'is_admin_or_root': _is_admin_or_root(user),
        })


# ── API: 用户管理（admin/root）────────────────────────────────────────────────

class UserListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_admin_or_root(request.user):
            return Response({'error': True, 'message': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        users = []
        for u in User.objects.all().order_by('id'):
            profile = _get_profile(u)
            role = 'root' if u.is_superuser else (profile.role if profile else ROLE_QUERY)
            users.append({
                'id': u.id,
                'username': u.username,
                'role': role,
                'is_active': u.is_active,
                'date_joined': u.date_joined.strftime('%Y-%m-%d %H:%M'),
            })
        return Response({'error': False, 'users': users})

    def post(self, request):
        """新增用户（admin/root）"""
        if not _is_admin_or_root(request.user):
            return Response({'error': True, 'message': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')
        role     = request.data.get('role', ROLE_QUERY)
        if not username or not password:
            return Response({'error': True, 'message': '用户名和密码不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if len(password) < 6:
            return Response({'error': True, 'message': '密码至少 6 位'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username=username).exists():
            return Response({'error': True, 'message': '用户名已存在'}, status=status.HTTP_400_BAD_REQUEST)
        if role not in (ROLE_ADMIN, ROLE_QUERY):
            role = ROLE_QUERY
        if role == ROLE_ADMIN and not request.user.is_superuser:
            return Response({'error': True, 'message': '只有 root 可以创建 admin 角色用户'}, status=status.HTTP_403_FORBIDDEN)
        user = User.objects.create_user(username=username, password=password)
        UserProfile.objects.create(user=user, role=role)
        return Response({'error': False, 'message': '用户创建成功', 'id': user.id}, status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request, user_id):
        """修改用户信息：用户名、角色、密码（admin/root；不可修改超级用户）"""
        if not _is_admin_or_root(request.user):
            return Response({'error': True, 'message': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': True, 'message': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)
        if target.is_superuser:
            return Response({'error': True, 'message': '不能修改超级用户'}, status=status.HTTP_400_BAD_REQUEST)

        # 修改用户名
        new_username = request.data.get('username', '').strip()
        if new_username and new_username != target.username:
            if User.objects.filter(username=new_username).exclude(id=user_id).exists():
                return Response({'error': True, 'message': '用户名已被占用'}, status=status.HTTP_400_BAD_REQUEST)
            target.username = new_username

        # 修改角色
        new_role = request.data.get('role', '')
        if new_role in (ROLE_ADMIN, ROLE_QUERY):
            if new_role == ROLE_ADMIN and not request.user.is_superuser:
                return Response({'error': True, 'message': '只有 root 用户可以授予 admin 角色'}, status=status.HTTP_403_FORBIDDEN)
            profile, _ = UserProfile.objects.get_or_create(user=target)
            profile.role = new_role
            profile.save()

        # 修改密码（空则不改）
        new_password = request.data.get('password', '')
        if new_password:
            if len(new_password) < 6:
                return Response({'error': True, 'message': '密码至少 6 位'}, status=status.HTTP_400_BAD_REQUEST)
            target.set_password(new_password)

        target.save()
        return Response({'error': False, 'message': '已更新'})

    def delete(self, request, user_id):
        """删除用户（仅 root）"""
        if not request.user.is_superuser:
            return Response({'error': True, 'message': '只有 root 用户可以删除账号'}, status=status.HTTP_403_FORBIDDEN)
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': True, 'message': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)
        if target.is_superuser:
            return Response({'error': True, 'message': '不能删除超级用户'}, status=status.HTTP_400_BAD_REQUEST)
        target.delete()
        return Response({'error': False, 'message': '已删除'})


# ── API: 用户组管理 ───────────────────────────────────────────────────────────

class GroupListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if _is_admin_or_root(request.user):
            qs = InstanceGroup.objects.all()
        else:
            qs = request.user.instance_groups.all()
        groups = []
        for g in qs.order_by('id'):
            members = [
                {'id': m.user.id, 'username': m.user.username}
                for m in g.memberships.select_related('user').all()
            ]
            groups.append({
                'id': g.id,
                'name': g.name,
                'description': g.description,
                'instances': g.instances,
                'members': members,
                'created_at': g.created_at.strftime('%Y-%m-%d %H:%M'),
            })
        return Response({'error': False, 'groups': groups})

    def post(self, request):
        if not _is_admin_or_root(request.user):
            return Response({'error': True, 'message': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        name = request.data.get('name', '').strip()
        description = request.data.get('description', '')
        if not name:
            return Response({'error': True, 'message': '组名不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if InstanceGroup.objects.filter(name=name).exists():
            return Response({'error': True, 'message': '组名已存在'}, status=status.HTTP_400_BAD_REQUEST)
        group = InstanceGroup.objects.create(
            name=name, description=description, created_by=request.user
        )
        return Response({'error': False, 'message': '创建成功', 'id': group.id})


class GroupDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_group(self, group_id):
        try:
            return InstanceGroup.objects.get(id=group_id)
        except InstanceGroup.DoesNotExist:
            return None

    def put(self, request, group_id):
        """更新组名/描述"""
        if not _is_admin_or_root(request.user):
            return Response({'error': True, 'message': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        group = self._get_group(group_id)
        if not group:
            return Response({'error': True, 'message': '组不存在'}, status=status.HTTP_404_NOT_FOUND)
        name = request.data.get('name', group.name).strip()
        if not name:
            return Response({'error': True, 'message': '组名不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if InstanceGroup.objects.filter(name=name).exclude(id=group_id).exists():
            return Response({'error': True, 'message': '组名已存在'}, status=status.HTTP_400_BAD_REQUEST)
        group.name = name
        group.description = request.data.get('description', group.description)
        group.save()
        return Response({'error': False, 'message': '已更新'})

    def delete(self, request, group_id):
        """删除组（仅 root）"""
        if not request.user.is_superuser:
            return Response({'error': True, 'message': '只有 root 用户可以删除组'}, status=status.HTTP_403_FORBIDDEN)
        group = self._get_group(group_id)
        if not group:
            return Response({'error': True, 'message': '组不存在'}, status=status.HTTP_404_NOT_FOUND)
        group.delete()
        return Response({'error': False, 'message': '已删除'})


class GroupMemberView(APIView):
    """添加 / 移除组成员"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, group_id):
        if not _is_admin_or_root(request.user):
            return Response({'error': True, 'message': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        try:
            group = InstanceGroup.objects.get(id=group_id)
        except InstanceGroup.DoesNotExist:
            return Response({'error': True, 'message': '组不存在'}, status=status.HTTP_404_NOT_FOUND)
        user_id = request.data.get('user_id')
        try:
            user = User.objects.get(id=user_id)
        except (User.DoesNotExist, TypeError):
            return Response({'error': True, 'message': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)
        _, created = GroupMembership.objects.get_or_create(
            user=user, group=group, defaults={'added_by': request.user}
        )
        msg = '已添加' if created else '该用户已在组中'
        return Response({'error': False, 'message': msg})

    def delete(self, request, group_id, user_id):
        if not _is_admin_or_root(request.user):
            return Response({'error': True, 'message': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        deleted, _ = GroupMembership.objects.filter(group_id=group_id, user_id=user_id).delete()
        if deleted:
            return Response({'error': False, 'message': '已移除'})
        return Response({'error': True, 'message': '成员不存在'}, status=status.HTTP_404_NOT_FOUND)


class GroupInstanceView(APIView):
    """添加 / 移除组内实例"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, group_id):
        """添加实例 {ip, port}"""
        if not _is_admin_or_root(request.user):
            return Response({'error': True, 'message': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        try:
            group = InstanceGroup.objects.get(id=group_id)
        except InstanceGroup.DoesNotExist:
            return Response({'error': True, 'message': '组不存在'}, status=status.HTTP_404_NOT_FOUND)
        ip = request.data.get('ip', '').strip()
        try:
            port = int(request.data.get('port', 0))
        except (TypeError, ValueError):
            port = 0
        if not ip or not port:
            return Response({'error': True, 'message': 'ip 和 port 不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if group.has_instance(ip, port):
            return Response({'error': False, 'message': '实例已在组中'})
        instances = list(group.instances or [])
        instances.append({'ip': ip, 'port': port})
        group.instances = instances
        group.save()
        return Response({'error': False, 'message': '已添加'})

    def delete(self, request, group_id):
        """移除实例 {ip, port}"""
        if not _is_admin_or_root(request.user):
            return Response({'error': True, 'message': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        try:
            group = InstanceGroup.objects.get(id=group_id)
        except InstanceGroup.DoesNotExist:
            return Response({'error': True, 'message': '组不存在'}, status=status.HTTP_404_NOT_FOUND)
        ip = request.data.get('ip', '').strip()
        try:
            port = int(request.data.get('port', 0))
        except (TypeError, ValueError):
            port = 0
        instances = [
            i for i in (group.instances or [])
            if not (str(i.get('ip')) == ip and int(i.get('port', 0)) == port)
        ]
        group.instances = instances
        group.save()
        return Response({'error': False, 'message': '已移除'})
