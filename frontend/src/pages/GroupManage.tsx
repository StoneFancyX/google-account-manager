import React, { useState, useEffect, useRef } from 'react';
import {
  Card,
  Button,
  Modal,
  Form,
  Input,
  Select,
  message,
  Tag,
  Typography,
  Flex,
  Dropdown,
  Empty,
  Spin,
  Row,
  Col,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  UserAddOutlined,
  CrownOutlined,
  MoreOutlined,
  TeamOutlined,
  UserOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  SearchOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import {
  getGroupList,
  getGroup,
  createGroup,
  updateGroup,
  deleteGroup,
  addAccountToGroup,
  setMainAccount,
  getAccounts,
} from '@/api';
import type { Group, Account } from '@/types';
import { maskEmail } from '@/utils/mask';
import GroupDetail from './GroupDetail';

const { TextArea } = Input;
const { Text } = Typography;

const GroupManage: React.FC = () => {
  const [groups, setGroups] = useState<Group[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingGroup, setEditingGroup] = useState<Group | null>(null);
  const [masked, setMasked] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [form] = Form.useForm();
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  const loadIdRef = useRef(0);

  // 二级视图: 详情页
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);

  useEffect(() => {
    loadGroups();
    loadAccounts();
  }, []);

  const handleSearchChange = (value: string) => {
    setSearchText(value);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      loadGroups(value);
    }, 300);
  };

  const loadGroups = async (search?: string) => {
    const id = ++loadIdRef.current;
    setLoading(true);
    try {
      const { data } = await getGroupList(search || undefined);
      if (loadIdRef.current === id) setGroups(data.groups);
    } catch {
      if (loadIdRef.current === id) message.error('加载分组失败');
    } finally {
      if (loadIdRef.current === id) setLoading(false);
    }
  };

  const loadAccounts = async () => {
    try {
      const { data } = await getAccounts('', undefined, undefined, 1, 999);
      setAccounts(data.accounts);
    } catch (error) {
      console.error('加载账号失败:', error);
    }
  };

  const handleAdd = () => {
    setEditingGroup(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (group: Group) => {
    setEditingGroup(group);
    form.setFieldsValue(group);
    setModalVisible(true);
  };

  const handleDelete = (id: number) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个分组吗？组内账号不会被删除。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteGroup(id);
          message.success('分组已删除');
          loadGroups();
        } catch {
          message.error('删除失败');
        }
      },
    });
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingGroup) {
        await updateGroup(editingGroup.id, values);
        message.success('分组更新成功');
      } else {
        if (!values.main_account_id) {
          message.error('请选择主号');
          return;
        }

        const mainAccount = accounts.find((acc) => acc.id === values.main_account_id);
        if (!mainAccount) {
          message.error('主号不存在');
          return;
        }

        const { data } = await createGroup({
          name: mainAccount.email,
          notes: values.notes || '',
        });
        const groupId = data.id;

        await addAccountToGroup(groupId, values.main_account_id);
        await setMainAccount(groupId, values.main_account_id);

        message.success('分组创建成功');
      }
      setModalVisible(false);
      loadGroups();
    } catch (error: any) {
      if (error.response) {
        message.error(error.response.data.detail || '保存失败');
      }
    }
  };

  const memberCount = (group: Group) => group.accounts?.length ?? 0;

  // 如果选中了分组 → 显示详情页
  if (selectedGroupId !== null) {
    return (
      <GroupDetail
        groupId={selectedGroupId}
        onBack={() => { setSelectedGroupId(null); loadGroups(); }}
      />
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 工具栏 */}
      <Flex justify="space-between" align="center" style={{ marginBottom: 20, flexShrink: 0 }} wrap gap={12}>
        <Flex gap={8} wrap>
          <Input
            placeholder="搜索邮箱（支持搜子号）"
            prefix={<SearchOutlined style={{ color: '#bfbfbf' }} />}
            style={{ width: 260 }}
            onChange={(e) => handleSearchChange(e.target.value)}
            allowClear
          />
        </Flex>
        <Flex gap={8} align="center">
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            创建分组
          </Button>
          <Tooltip title={masked ? '显示邮箱' : '隐藏邮箱'}>
            <Button
              type="text"
              icon={masked ? <EyeInvisibleOutlined /> : <EyeOutlined />}
              onClick={() => setMasked((v) => !v)}
            />
          </Tooltip>
        </Flex>
      </Flex>

      {/* 分组卡片列表 */}
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', minHeight: 0 }}>
        <Spin spinning={loading}>
          {groups.length === 0 && !loading ? (
            <Empty description="暂无分组" style={{ marginTop: 60 }} />
          ) : (
            <Row gutter={[16, 16]}>
              {groups.map((group) => {
                const count = memberCount(group);
                const subAccounts = (group.accounts || []).filter(
                  (acc) => acc.id !== group.main_account_id
                );

                return (
                  <Col key={group.id} xs={24} sm={12} lg={8} xl={6}>
                    <Card
                      size="small"
                      className="hover-card"
                      hoverable
                      onClick={() => setSelectedGroupId(group.id)}
                      style={{
                        borderRadius: 12,
                        border: '1px solid #f0f0f0',
                        transition: 'all 0.2s',
                        height: '100%',
                        cursor: 'pointer',
                      }}
                      styles={{
                        body: { padding: '16px 16px 12px' },
                      }}
                    >
                      {/* 顶部: 分组名 + 操作 */}
                      <Flex justify="space-between" align="flex-start" style={{ marginBottom: 10 }}>
                        <Flex align="center" gap={8} style={{ flex: 1, minWidth: 0 }}>
                          <TeamOutlined style={{ color: '#722ed1', fontSize: 18, flexShrink: 0 }} />
                          <Tooltip title={group.name}>
                            <Text strong ellipsis style={{ fontSize: 13, maxWidth: '100%' }}>
                              {masked && group.name.includes('@') ? maskEmail(group.name) : group.name}
                            </Text>
                          </Tooltip>
                        </Flex>
                        <Dropdown
                          menu={{
                            items: [
                              {
                                key: 'edit',
                                icon: <EditOutlined />,
                                label: '编辑',
                                onClick: (e) => { e.domEvent.stopPropagation(); handleEdit(group); },
                              },
                              { type: 'divider' },
                              {
                                key: 'delete',
                                icon: <DeleteOutlined />,
                                label: '删除',
                                danger: true,
                                onClick: (e) => { e.domEvent.stopPropagation(); handleDelete(group.id); },
                              },
                            ],
                          }}
                          trigger={['click']}
                        >
                          <Button
                            type="text"
                            size="small"
                            icon={<MoreOutlined style={{ color: '#8c8c8c' }} />}
                            style={{ flexShrink: 0, marginLeft: 4 }}
                            onClick={(e) => e.stopPropagation()}
                          />
                        </Dropdown>
                      </Flex>

                      {/* 中部: 订阅状态 + 成员数 */}
                      <Flex gap={6} align="center" wrap style={{ marginBottom: 8 }}>
                        {(() => {
                          const mainAcc = (group.accounts || []).find(a => a.id === group.main_account_id);
                          return (
                            <>
                              {mainAcc?.subscription_status === 'ultra' && (
                                <Tag color="purple" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>
                                  Ultra
                                </Tag>
                              )}
                              {mainAcc?.subscription_status === 'ultra' && mainAcc?.subscription_expiry && (
                                <Tag color="default" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>
                                  重置于 {mainAcc.subscription_expiry}
                                </Tag>
                              )}
                            </>
                          );
                        })()}
                        {subAccounts.length > 0 && (
                          <Tag
                            color="default"
                            style={{ margin: 0, fontSize: 11, lineHeight: '18px', padding: '0 6px' }}
                          >
                            <UserOutlined style={{ marginRight: 3 }} />
                            {subAccounts.length} 个子号
                          </Tag>
                        )}
                      </Flex>

                      {/* 子号列表 (全部显示，含待接受) */}
                      {subAccounts.length > 0 && (
                        <Flex vertical gap={3} style={{ marginBottom: group.notes ? 8 : 4 }}>
                          {subAccounts.map((acc) => (
                            <Text
                              key={acc.id}
                              type="secondary"
                              ellipsis
                              style={{ fontSize: 11, paddingLeft: 4 }}
                            >
                              {acc.is_family_pending
                                ? <ClockCircleOutlined style={{ marginRight: 4, fontSize: 10, color: '#fa8c16' }} />
                                : <UserOutlined style={{ marginRight: 4, fontSize: 10 }} />}
                              {masked ? maskEmail(acc.email) : acc.email}
                              {acc.is_family_pending && (
                                <span style={{ color: '#fa8c16', marginLeft: 4, fontSize: 10 }}>待接受</span>
                              )}
                            </Text>
                          ))}
                        </Flex>
                      )}

                      {/* 底部: 备注 */}
                      {group.notes && (
                        <Text
                          type="secondary"
                          ellipsis
                          style={{ fontSize: 11, display: 'block', color: '#bfbfbf' }}
                        >
                          {group.notes}
                        </Text>
                      )}
                    </Card>
                  </Col>
                );
              })}
            </Row>
          )}
        </Spin>

        {/* 底部统计 */}
        {groups.length > 0 && (
          <Flex justify="flex-end" style={{ marginTop: 16 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              共 {groups.length} 个分组
            </Text>
          </Flex>
        )}
      </div>

      {/* 创建/编辑分组弹窗 */}
      <Modal
        title={editingGroup ? '编辑分组' : '创建分组'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={handleSubmit}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {editingGroup && (
            <Form.Item
              name="name"
              label="分组名称"
              rules={[{ required: true, message: '请输入分组名称' }]}
            >
              <Input placeholder="如: 工作账号组" />
            </Form.Item>
          )}
          {!editingGroup && (
            <Form.Item
              name="main_account_id"
              label="选择主号"
              rules={[{ required: true, message: '请选择主号' }]}
            >
              <Select
                placeholder="选择一个账号作为主号"
                showSearch
                optionFilterProp="label"
                options={accounts
                  .filter((acc) => !acc.group_id)
                  .map((acc) => ({ label: acc.email, value: acc.id }))}
              />
            </Form.Item>
          )}
          <Form.Item name="notes" label="备注">
            <TextArea rows={3} placeholder="其他信息..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default GroupManage;
