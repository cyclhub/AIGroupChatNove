<template>
  <main class="app-shell">
    <section v-if="!currentUser" class="auth-page">
      <div class="auth-card">
        <div class="auth-form-card">
          <div class="auth-title">
            <strong>ai群聊小说</strong>
            <span>{{ authMode === 'login' ? '登录后进入你的专属书架' : '创建账号并配置大模型' }}</span>
          </div>
          <div class="auth-tabs">
            <button :class="{ active: authMode === 'login' }" @click="setAuthMode('login')">登录</button>
            <button :class="{ active: authMode === 'register' }" @click="setAuthMode('register')">注册</button>
          </div>

          <el-form label-position="top" class="auth-form">
            <el-form-item label="账号">
              <el-input v-model="authForm.username" placeholder="请输入账号" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="authForm.password" type="password" show-password placeholder="至少 6 位" />
            </el-form-item>
            <el-checkbox v-if="authMode === 'login'" v-model="authRemember" class="remember-check">记住我</el-checkbox>

            <template v-if="authMode === 'register'">
              <div class="auth-model-tip">
                <strong>大模型配置</strong>
                <span>注册时会真实调用一次模型，验证通过后才会创建账号。</span>
              </div>
              <el-form-item label="供应商">
                <el-select v-model="authForm.api_provider" placeholder="选择模型供应商" @change="applyAuthProviderDefaults">
                  <el-option v-for="provider in modelProviders" :key="provider.provider" :label="provider.label" :value="provider.provider" />
                </el-select>
              </el-form-item>
              <el-form-item label="模型">
                <el-input v-model="authForm.api_model" placeholder="请填写模型名" />
              </el-form-item>
              <el-form-item label="Base URL">
                <el-input v-model="authForm.api_base_url" placeholder="OpenAI 兼容接口地址" />
              </el-form-item>
              <el-form-item label="API Key">
                <el-input v-model="authForm.api_key" type="password" show-password placeholder="请输入 API Key" />
              </el-form-item>
            </template>

            <el-button class="auth-submit" type="primary" :loading="authLoading" @click="submitAuth">
              {{ authLoading ? '请稍候...' : authMode === 'login' ? '进入书架' : '验证并注册' }}
            </el-button>
          </el-form>
        </div>
      </div>
    </section>

    <template v-else>
    <header class="topbar" :class="{ 'sub-page-topbar': currentPage !== 'novels' }">
      <div class="left-nav">
        <button v-if="currentPage !== 'novels'" class="back-btn" @click="goBack">‹</button>
        <span v-if="currentPage === 'novels'" class="top-brand">ai群聊小说</span>
      </div>
      <div class="title-block">
        <strong v-if="currentPage !== 'novels'">{{ pageTitle }}</strong>
      </div>
      <button v-if="currentPage === 'novels'" class="logout-btn" @click="logout">退出</button>
      <span v-else></span>
    </header>

    <section v-if="currentPage === 'novels'" class="page home-page">
      <div class="hero-card">
        <div>
          <p>AI 小说书架</p>
          <h1>把小说整理成可以聊天式阅读的书架</h1>
          <span>上传、拆章、解析，然后像翻书一样进入群聊剧情。</span>
        </div>
        <button class="upload-book-btn" @click="openUploadDialog">+ 上传新书</button>
      </div>

      <div class="shelf-header">
        <div>
          <strong>我的书架</strong>
          <span>{{ novelTotal }} 本小说</span>
        </div>
        <div class="shelf-actions">
          <button class="shelf-action muted" @click="openModelDialog">模型</button>
          <button class="shelf-action" @click="openUploadDialog">添加</button>
        </div>
      </div>

      <div v-if="novels.length" class="novel-list shelf-grid">
        <article v-for="novel in novels" :key="novel.id" class="novel-card" @click="selectNovel(novel)">
          <div class="book-cover">
            <div class="book-spine"></div>
            <div class="book-shine"></div>
            <span class="book-badge">{{ getStatusText(novel.status) }}</span>
            <strong>{{ novel.title }}</strong>
            <small>AI 群聊小说</small>
          </div>
          <div class="novel-main">
            <h3>{{ novel.title }}</h3>
            <p>{{ getNovelProgress(novel) }}% 已解析</p>
            <div class="book-progress">
              <i :style="{ width: getNovelProgress(novel) + '%' }"></i>
            </div>
          </div>
          <div class="novel-actions">
            <span>{{ novel.processed_chapters }}/{{ novel.total_chapters || 0 }}章</span>
            <button class="delete-link" @click.stop="deleteNovel(novel)">删除</button>
          </div>
        </article>
      </div>
      <el-empty v-else description="还没有上传小说" />
      <div v-if="novelLoadingMore" class="list-loading">正在加载更多小说...</div>
      <div v-else-if="!novelHasMore && novels.length" class="list-loading">书架已全部加载</div>
    </section>

    <section v-if="currentPage === 'chapters'" class="page chapters-page">
      <div class="process-panel">
        <div class="process-head">
          <div>
            <span>解析进度</span>
            <strong>{{ selectedNovel?.processed_chapters || 0 }}/{{ selectedNovel?.total_chapters || 0 }}</strong>
          </div>
          <el-tag :type="getStatusType(selectedNovel?.status)">{{ getStatusText(selectedNovel?.status) }}</el-tag>
        </div>
        <el-progress :percentage="novelProgress" :stroke-width="10" />
        <div class="actions">
          <el-button v-if="selectedNovel?.status === 'uploaded'" type="primary" :loading="splitting" @click="splitNovel">
            拆分章节
          </el-button>
          <el-button v-if="canProcess" type="success" @click="openProcessDialog">选择章节解析</el-button>
          <el-button v-if="isProcessing" type="danger" plain @click="cancelProcess">取消解析</el-button>
        </div>
        <div class="chapter-jump">
          <el-input-number v-model="jumpChapterNumber" :min="1" :max="selectedNovel?.total_chapters || 1" />
          <el-button :disabled="!selectedNovel?.total_chapters" @click="jumpToChapter">跳转到该章</el-button>
        </div>
      </div>

      <div class="chapter-list">
        <article
          v-for="chapter in chapters"
          :key="chapter.id"
          class="chapter-row"
          :class="{ processing: isChapterProcessing(chapter) }"
          :data-chapter-number="chapter.chapter_number"
          @click="viewChapter(chapter)"
        >
          <div class="chapter-index">{{ chapter.chapter_number }}</div>
          <div class="chapter-info">
            <h3>{{ chapter.title }}</h3>
            <p>{{ chapter.is_processed ? '已生成对话流' : '未解析' }}</p>
          </div>
          <el-button
            size="small"
            :type="chapter.is_processed ? 'warning' : 'primary'"
            plain
            :disabled="isProcessing"
            @click.stop="processSingleChapter(chapter)"
          >
            {{ chapter.is_processed ? '重新解析' : '转换' }}
          </el-button>
        </article>
      </div>
      <div v-if="chapterLoadingMore" class="list-loading">正在加载更多章节...</div>
      <div v-else-if="!chapterHasMore && chapters.length" class="list-loading">章节已全部加载</div>
    </section>

    <section v-if="currentPage === 'content'" class="reader-page">
      <div class="reader-toolbar" :class="{ expanded: readerToolsOpen }">
        <button class="reader-toolbar-toggle" @click="readerToolsOpen = !readerToolsOpen">
          <span></span>
        </button>
        <div v-show="readerToolsOpen" class="reader-toolbar-body">
          <div class="font-tools">
            <span>字号</span>
            <button @click="changeFontSize(-1)">A-</button>
            <strong>{{ readerFontSize }}</strong>
            <button @click="changeFontSize(1)">A+</button>
          </div>
          <div class="reader-tabs">
            <button :class="{ active: contentTab === 'dialogue' }" @click="contentTab = 'dialogue'">群聊阅读</button>
            <button :class="{ active: contentTab === 'original' }" @click="contentTab = 'original'">原文</button>
          </div>
          <div v-if="contentTab === 'dialogue'" class="dialogue-mode-switch">
            <button :class="{ active: dialogueRevealMode === 'scroll' }" @click="setDialogueRevealMode('scroll')">滚动阅读</button>
            <button :class="{ active: dialogueRevealMode === 'tap' }" @click="setDialogueRevealMode('tap')">点按收消息</button>
          </div>
        </div>
      </div>

      <div
        v-show="contentTab === 'dialogue'"
        ref="chatWindowRef"
        class="chat-window"
        :class="{ 'tap-reveal-mode': dialogueRevealMode === 'tap' }"
        :style="readerStyle"
        @click="handleChatWindowClick"
        @scroll.passive="handleChatScroll"
      >
        <template v-if="visibleDialogues.length">
          <div
            v-for="dialogue in visibleDialogues"
            :key="dialogue.id"
            :data-message-id="dialogue.id"
            class="message-item pop-message"
            :class="{ narrator: isNarrator(dialogue), 'chapter-marker': dialogue.type === 'chapter' }"
          >
            <div v-if="dialogue.type === 'chapter'" class="chapter-divider">{{ dialogue.text }}</div>
            <div v-else-if="isNarrator(dialogue)" class="narrator-bubble">{{ dialogue.text }}</div>
            <template v-else>
              <div class="avatar">{{ getAvatar(dialogue.character) }}</div>
              <div class="bubble">
                <div class="speaker">{{ dialogue.character }}</div>
                <div class="message-text">{{ dialogue.text }}</div>
              </div>
            </template>
          </div>
          <div v-if="nextChapterLoading" class="reader-loading">正在进入下一章...</div>
          <div v-if="prevChapterLoading" class="reader-loading">正在加载上一章...</div>
          <div v-if="readerEnded" class="reader-ending">已读到最后一章</div>
        </template>
        <el-empty v-else description="这一章还没有解析成对话流" />
      </div>

      <article
        v-show="contentTab === 'original'"
        ref="originalWindowRef"
        class="original-content"
        :style="readerStyle"
        @scroll.passive="handleOriginalScroll"
      >
        <section v-for="item in originalChapters" :key="item.id" :data-original-id="item.id" class="original-chapter">
          <h2 class="original-title">{{ item.chapter_number }}. {{ item.title }}</h2>
          <div class="original-body">{{ item.content }}</div>
        </section>
        <div v-if="prevOriginalLoading" class="reader-loading">正在加载上一章...</div>
        <div v-if="nextOriginalLoading" class="reader-loading">正在加载下一章...</div>
      </article>

      <div v-if="showReaderQuickPanel" class="reader-quick-mask" @click="showReaderQuickPanel = false">
        <div class="reader-quick-panel" @click.stop>
          <strong>{{ selectedChapter?.chapter_number }}. {{ selectedChapter?.title || '当前章节' }}</strong>
          <span>{{ contentTab === 'dialogue' ? '群聊阅读' : '原文阅读' }}</span>
          <div class="reader-quick-actions">
            <button :class="{ active: contentTab === 'dialogue' }" @click="switchReaderMode('dialogue')">群聊阅读</button>
            <button :class="{ active: contentTab === 'original' }" @click="switchReaderMode('original')">原文阅读</button>
          </div>
          <div v-if="contentTab === 'dialogue'" class="reader-quick-actions reader-quick-submodes">
            <button :class="{ active: dialogueRevealMode === 'scroll' }" @click="setDialogueRevealMode('scroll')">滚动阅读</button>
            <button :class="{ active: dialogueRevealMode === 'tap' }" @click="setDialogueRevealMode('tap')">点按收消息</button>
          </div>
          <div class="reader-quick-font">
            <button @click="changeFontSize(-1)">A-</button>
            <strong>{{ readerFontSize }}</strong>
            <button @click="changeFontSize(1)">A+</button>
          </div>
          <div class="reader-quick-jump">
            <el-input-number v-model="jumpChapterNumber" :min="1" :max="selectedNovel?.total_chapters || 1" />
            <button @click="jumpToChapterFromReader">跳转章节</button>
          </div>
          <button class="reader-quick-back" @click="closeReaderToChapters">返回目录</button>
        </div>
      </div>
    </section>

    <el-dialog v-model="showUploadDialog" title="" width="92%" class="upload-dialog" @closed="resetUploadState">
      <div class="upload-panel">
        <div class="upload-book-visual">
          <div class="book-spine"></div>
          <strong>TXT</strong>
        </div>
        <div class="upload-panel-copy">
          <strong>上传一本新小说</strong>
          <span>选择 TXT 文件，上传成功后进入书籍手动拆分章节。</span>
        </div>
      </div>
      <el-upload
        ref="uploadRef"
        drag
        :auto-upload="false"
        :on-change="handleFileChange"
        :on-remove="resetUploadState"
        :limit="1"
        accept=".txt"
        class="shelf-upload"
      >
        <div class="upload-copy">
          <strong>{{ uploadFile ? uploadFile.name : '点击选择 TXT 文件' }}</strong>
          <span>{{ uploadFile ? '已选择，点击上传即可' : '也可以拖拽文件到这里' }}</span>
        </div>
      </el-upload>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="uploadNovel">上传</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showUserDialog"
      :title="currentUser ? '模型设置' : '首次使用设置'"
      width="92%"
      :close-on-click-modal="!!currentUser"
      :show-close="!!currentUser"
      class="upload-dialog"
    >
      <div class="model-panel">
        <strong>{{ currentUser ? '更新你的大模型配置' : '创建用户并配置大模型' }}</strong>
        <span>保存前会先真实调用一次模型，验证通过后才会保存。</span>
      </div>
      <el-form label-width="82px" class="model-form">
        <el-form-item label="昵称">
          <el-input v-model="userForm.username" placeholder="例如：小华" />
        </el-form-item>
        <el-form-item label="供应商">
          <el-select v-model="userForm.api_provider" placeholder="选择模型供应商" @change="applyProviderDefaults">
            <el-option v-for="provider in modelProviders" :key="provider.provider" :label="provider.label" :value="provider.provider" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="userForm.api_model" placeholder="请填写模型名" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="userForm.api_base_url" placeholder="OpenAI 兼容接口地址" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="userForm.api_key" type="password" show-password :placeholder="currentUser ? '不填则保留原 API Key' : '请输入 API Key'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="currentUser" @click="showUserDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingUser" @click="saveUserConfig">
          {{ savingUser ? '正在验证...' : currentUser ? '验证并保存' : '验证并注册' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDeleteDialog" title="确认删除小说" width="90%" :close-on-click-modal="false">
      <div class="delete-confirm">
        <strong>《{{ pendingDeleteNovel?.title }}》</strong>
        <p>删除后会同时清空这本书的章节、解析后的群聊内容和上传文件，操作不可恢复。</p>
      </div>
      <template #footer>
        <el-button @click="showDeleteDialog = false">取消</el-button>
        <el-button type="danger" :loading="deletingNovel" @click="confirmDeleteNovel">确认删除</el-button>
      </template>
    </el-dialog>

    <div v-if="globalLoading" class="glass-loading">
      <div class="glass-loading-card">
        <div class="spinner"></div>
        <strong>{{ globalLoadingText }}</strong>
      </div>
    </div>

    <el-dialog v-model="showProcessDialog" title="选择解析范围" width="92%">
      <el-form label-width="88px">
        <el-form-item label="开始章节">
          <el-input-number v-model="processConfig.startChapter" :min="1" :max="selectedNovel?.total_chapters || 1" />
        </el-form-item>
        <el-form-item label="结束章节">
          <el-input-number
            v-model="processConfig.endChapter"
            :min="processConfig.startChapter"
            :max="selectedNovel?.total_chapters || 1"
          />
        </el-form-item>
      </el-form>
      <p class="dialog-tip">建议先解析 3 到 10 章看效果。已解析过的章节，选中后也会重新解析。</p>
      <template #footer>
        <el-button @click="showProcessDialog = false">取消</el-button>
        <el-button type="primary" @click="startBatchProcess">开始解析</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showProgressDialog" title="AI 正在解析" width="92%" :close-on-click-modal="false">
      <div class="loading-card">
        <div class="spinner"></div>
        <strong>{{ progressText }}</strong>
        <el-progress :percentage="processProgress" :stroke-width="12" />
        <p>已降低轮询频率，每 5 秒检查一次。取消后会等当前大模型请求返回，再停止下一章。</p>
      </div>
      <template #footer>
        <el-button @click="hideProgressDialog">先放后台</el-button>
        <el-button type="danger" plain @click="cancelProcess">取消解析</el-button>
      </template>
    </el-dialog>
    </template>
  </main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const currentPage = ref('novels')
const contentTab = ref('dialogue')
const userStorageKey = 'ai_chat_novel_session'
const currentUser = ref(null)
const modelProviders = ref([])
const showUserDialog = ref(false)
const savingUser = ref(false)
const authMode = ref('login')
const authLoading = ref(false)
const authRemember = ref(true)
const authForm = ref({
  username: '',
  password: '',
  api_provider: 'deepseek',
  api_base_url: 'https://api.deepseek.com',
  api_model: 'deepseek-chat',
  api_key: '',
})
const userForm = ref({
  username: '',
  api_provider: 'deepseek',
  api_base_url: 'https://api.deepseek.com',
  api_model: 'deepseek-chat',
  api_key: '',
})

const novels = ref([])
const novelPage = ref(1)
const novelPageSize = ref(20)
const novelTotal = ref(0)
const novelHasMore = ref(false)
const novelLoadingMore = ref(false)
const selectedNovel = ref(null)
const chapters = ref([])
const selectedChapter = ref(null)
const allDialogues = ref([])
const chapterContent = ref('')
const originalChapters = ref([])
const chapterPage = ref(1)
const chapterPageSize = ref(20)
const chapterTotal = ref(0)
const chapterHasMore = ref(false)
const chapterLoadingMore = ref(false)
const visibleMessageCount = ref(0)
const messageBatchSize = 10
const tapRevealInitialCount = 4
const tapRevealBottomGap = 92
const nextChapterLoading = ref(false)
const prevChapterLoading = ref(false)
const readerEnded = ref(false)
const readerAtStart = ref(false)
const loadedChapterIds = ref(new Set())
const loadedChapterMeta = ref(new Map())
const firstLoadedChapter = ref(null)
const lastLoadedChapter = ref(null)
const readerFontSize = ref(15)
const chatWindowRef = ref(null)
const originalWindowRef = ref(null)
const readerToolsOpen = ref(false)
const showReaderQuickPanel = ref(false)
const dialogueRevealMode = ref('scroll')
const restoringProgress = ref(false)
const restoringReaderSnapshot = ref(false)
const readingProgressKeyBase = 'ai_chat_novel_progress'
const prevOriginalLoading = ref(false)
const nextOriginalLoading = ref(false)
const originalAtStart = ref(false)
const originalAtEnd = ref(false)
const loadedOriginalChapterIds = ref(new Set())
const firstOriginalChapter = ref(null)
const lastOriginalChapter = ref(null)

const showUploadDialog = ref(false)
const showProcessDialog = ref(false)
const showProgressDialog = ref(false)
const showDeleteDialog = ref(false)
const uploading = ref(false)
const splitting = ref(false)
const deletingNovel = ref(false)
const pendingDeleteNovel = ref(null)
const globalLoading = ref(false)
const globalLoadingText = ref('处理中...')

const uploadFile = ref(null)
const uploadRef = ref(null)
const processConfig = ref({ startChapter: 1, endChapter: 10 })
const jumpChapterNumber = ref(1)
const processProgress = ref(0)
const processedCount = ref(0)
const totalCount = ref(0)
const processingRange = ref({ start: null, end: null })
const progressTimer = ref(null)
const polling = ref(false)

const pageTitle = computed(() => {
  if (currentPage.value === 'chapters') return selectedNovel.value?.title || '章节'
  if (currentPage.value === 'content') return selectedChapter.value?.title || '阅读'
  return '小说工坊'
})

const pageSubtitle = computed(() => {
  if (currentPage.value === 'chapters') return '拆章与解析'
  if (currentPage.value === 'content') return contentTab.value === 'dialogue' ? 'QQ群聊模式' : '原文预览'
  return '手机阅读版'
})

const isProcessing = computed(() => selectedNovel.value?.status === 'processing')
const canProcess = computed(() => ['split', 'failed', 'cancelled', 'completed'].includes(selectedNovel.value?.status))
const isChapterProcessing = (chapter) => {
  if (!isProcessing.value) return false
  const start = processingRange.value.start
  const end = processingRange.value.end
  if (!start) return false
  const upper = end || start
  return chapter.chapter_number >= start && chapter.chapter_number <= upper
}

const novelProgress = computed(() => {
  const total = selectedNovel.value?.total_chapters || 0
  return total ? Math.round(((selectedNovel.value?.processed_chapters || 0) / total) * 100) : 0
})

const progressText = computed(() => `已解析 ${processedCount.value} / ${totalCount.value} 章`)
const visibleDialogues = computed(() => allDialogues.value.slice(0, visibleMessageCount.value))
const readerStyle = computed(() => ({
  '--reader-font-size': `${readerFontSize.value}px`,
  '--reader-line-height': readerFontSize.value >= 19 ? '1.86' : '1.72',
}))
const currentProvider = computed(() => modelProviders.value.find((item) => item.provider === userForm.value.api_provider))
const currentAuthProvider = computed(() => modelProviders.value.find((item) => item.provider === authForm.value.api_provider))

const getNovelProgress = (novel) => {
  const total = novel.total_chapters || 0
  return total ? Math.round(((novel.processed_chapters || 0) / total) * 100) : 0
}

axios.interceptors.request.use((config) => {
  if (currentUser.value?.token) {
    config.headers = config.headers || {}
    config.headers['X-Auth-Token'] = currentUser.value.token
  }
  return config
})

axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && currentUser.value) {
      clearLocalUser()
      resetSessionState()
      ElMessage.warning('登录已过期，请重新登录')
    }
    return Promise.reject(error)
  },
)

const loadLocalUser = () => {
  try {
    currentUser.value = JSON.parse(localStorage.getItem(userStorageKey) || sessionStorage.getItem(userStorageKey) || 'null')
  } catch (error) {
    currentUser.value = null
  }
}

const saveLocalUser = (user, remember = true) => {
  currentUser.value = user
  const storage = remember ? localStorage : sessionStorage
  const otherStorage = remember ? sessionStorage : localStorage
  storage.setItem(userStorageKey, JSON.stringify(user))
  otherStorage.removeItem(userStorageKey)
}

const clearLocalUser = () => {
  currentUser.value = null
  localStorage.removeItem(userStorageKey)
  sessionStorage.removeItem(userStorageKey)
}

const resetSessionState = () => {
  stopPolling()
  currentPage.value = 'novels'
  selectedNovel.value = null
  selectedChapter.value = null
  novels.value = []
  chapters.value = []
  allDialogues.value = []
  originalChapters.value = []
  novelPage.value = 1
  novelTotal.value = 0
  novelHasMore.value = false
}

const hydrateCurrentUser = async () => {
  const remembered = !!localStorage.getItem(userStorageKey)
  loadLocalUser()
  if (!currentUser.value?.token) {
    return false
  }
  try {
    const res = await axios.get('/api/auth/me')
    saveLocalUser(res.data, remembered)
    return true
  } catch (error) {
    clearLocalUser()
    return false
  }
}

const fetchModelProviders = async () => {
  const res = await axios.get('/api/model-providers')
  modelProviders.value = res.data || []
}

const ensureModelProviders = async () => {
  if (modelProviders.value.length) return true
  try {
    await fetchModelProviders()
    return true
  } catch (error) {
    ElMessage.error('无法连接后端服务，请确认 Flask 后端已启动')
    return false
  }
}

const setAuthMode = async (mode) => {
  authMode.value = mode
  if (mode === 'register' && await ensureModelProviders()) {
    applyAuthProviderDefaults()
  }
}

const applyProviderDefaults = () => {
  const provider = currentProvider.value
  if (!provider) return
  userForm.value.api_base_url = provider.base_url
  userForm.value.api_model = provider.models?.[0] || ''
}

const applyAuthProviderDefaults = () => {
  const provider = currentAuthProvider.value
  if (!provider) return
  authForm.value.api_base_url = provider.base_url
  authForm.value.api_model = provider.models?.[0] || ''
}

const submitAuth = async () => {
  if (!authForm.value.username.trim()) {
    ElMessage.warning('请输入账号')
    return
  }
  if (authForm.value.password.length < 6) {
    ElMessage.warning('密码至少需要 6 位')
    return
  }
  if (authMode.value === 'register' && !authForm.value.api_key.trim()) {
    ElMessage.warning('注册时需要填写大模型 API Key')
    return
  }

  authLoading.value = true
  try {
    if (authMode.value === 'register') {
      const providersReady = await ensureModelProviders()
      if (!providersReady) return
      ElMessage.info('正在验证模型配置...')
    }
    const payload = { ...authForm.value }
    const res = authMode.value === 'login'
      ? await axios.post('/api/login', {
          username: payload.username,
          password: payload.password,
        })
      : await axios.post('/api/users', payload)
    saveLocalUser(res.data.user, authMode.value === 'login' ? authRemember.value : true)
    ElMessage.success(authMode.value === 'login' ? '登录成功' : '注册成功')
    await refreshNovels()
  } catch (error) {
    ElMessage.error(error.response?.data?.error || (authMode.value === 'login' ? '登录失败' : '注册失败'))
  } finally {
    authLoading.value = false
  }
}

const logout = async () => {
  try {
    await axios.post('/api/logout')
  } catch (error) {
    // 本地退出优先，不因为网络问题卡住用户。
  }
  clearLocalUser()
  resetSessionState()
  authMode.value = 'login'
  ElMessage.success('已退出登录')
}

const openModelDialog = () => {
  ensureModelProviders()
  if (currentUser.value) {
    userForm.value = {
      username: currentUser.value.username || '',
      api_provider: currentUser.value.api_provider || 'deepseek',
      api_base_url: currentUser.value.api_base_url || 'https://api.deepseek.com',
      api_model: currentUser.value.api_model || 'deepseek-chat',
      api_key: '',
    }
  }
  showUserDialog.value = true
}

const saveUserConfig = async () => {
  if (!userForm.value.username.trim()) {
    ElMessage.warning('请输入昵称')
    return
  }
  if (!currentUser.value && !userForm.value.api_key.trim()) {
    ElMessage.warning('首次注册需要填写 API Key')
    return
  }

  savingUser.value = true
  try {
    const payload = { ...userForm.value }
    ElMessage.info('正在验证模型配置...')
    const res = currentUser.value
      ? await axios.put(`/api/users/${currentUser.value.id}/model`, payload)
      : await axios.post('/api/users', payload)
    saveLocalUser(res.data.user)
    showUserDialog.value = false
    ElMessage.success(currentUser.value ? '模型设置已保存' : '注册成功')
    await refreshNovels()
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '保存失败')
  } finally {
    savingUser.value = false
  }
}

const fetchNovels = async (append = false) => {
  if (novelLoadingMore.value) return
  novelLoadingMore.value = true
  try {
    const res = await axios.get('/api/novels', {
      params: {
        page: novelPage.value,
        page_size: novelPageSize.value,
      },
    })
    const items = res.data.items || []
    novels.value = append ? [...novels.value, ...items] : items
    novelTotal.value = res.data.total || 0
    novelHasMore.value = novelPage.value < (res.data.pages || 0)
    if (selectedNovel.value) {
      const fresh = items.find((item) => item.id === selectedNovel.value.id)
      if (fresh) selectedNovel.value = fresh
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '获取小说列表失败')
  } finally {
    novelLoadingMore.value = false
  }
}

const refreshNovels = async () => {
  novelPage.value = 1
  await fetchNovels(false)
}

const loadMoreNovels = async () => {
  if (currentPage.value !== 'novels' || !novelHasMore.value || novelLoadingMore.value) return
  novelPage.value += 1
  await fetchNovels(true)
}

const fetchChapters = async (append = false) => {
  if (!selectedNovel.value) return
  if (chapterLoadingMore.value) return
  chapterLoadingMore.value = true
  try {
    const res = await axios.get(`/api/novel/${selectedNovel.value.id}/chapters`, {
      params: {
        page: chapterPage.value,
        page_size: chapterPageSize.value,
      },
    })
    const items = res.data.items || []
    chapters.value = append ? [...chapters.value, ...items] : items
    chapterTotal.value = res.data.total || 0
    chapterHasMore.value = chapterPage.value < (res.data.pages || 0)
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '获取章节失败')
  } finally {
    chapterLoadingMore.value = false
  }
}

const selectNovel = async (novel) => {
  resetNovelViewState()
  selectedNovel.value = novel
  currentPage.value = 'chapters'
  chapterPage.value = 1
  await syncProcessStatus()
  await fetchChapters()
  if (novel.total_chapters > 0) {
    processConfig.value.startChapter = 1
    processConfig.value.endChapter = Math.min(10, novel.total_chapters)
    jumpChapterNumber.value = 1
  }
  if (selectedNovel.value?.status === 'processing') {
    startPolling()
  }

  await restoreReadingProgress(novel.id)
}

const resetNovelViewState = () => {
  chapters.value = []
  selectedChapter.value = null
  allDialogues.value = []
  chapterContent.value = ''
  originalChapters.value = []
  chapterPage.value = 1
  chapterTotal.value = 0
  chapterHasMore.value = false
  chapterLoadingMore.value = false
  visibleMessageCount.value = 0
  nextChapterLoading.value = false
  prevChapterLoading.value = false
  readerEnded.value = false
  readerAtStart.value = false
  loadedChapterIds.value = new Set()
  firstLoadedChapter.value = null
  lastLoadedChapter.value = null
  prevOriginalLoading.value = false
  nextOriginalLoading.value = false
  originalAtStart.value = false
  originalAtEnd.value = false
  loadedOriginalChapterIds.value = new Set()
  firstOriginalChapter.value = null
  lastOriginalChapter.value = null
  processingRange.value = { start: null, end: null }
}

const changeChapterPage = async (page) => {
  chapterPage.value = page
  await fetchChapters()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const loadMoreChapters = async () => {
  if (currentPage.value !== 'chapters' || !chapterHasMore.value || chapterLoadingMore.value) return
  chapterPage.value += 1
  await fetchChapters(true)
}

const deleteNovel = async (novel) => {
  pendingDeleteNovel.value = novel
  showDeleteDialog.value = true
}

const confirmDeleteNovel = async () => {
  const novel = pendingDeleteNovel.value
  if (!novel) return

  deletingNovel.value = true
  showDeleteDialog.value = false
  globalLoadingText.value = '正在删除小说...'
  globalLoading.value = true
  try {
    await axios.delete(`/api/novel/${novel.id}`)
    ElMessage.success('小说已删除')
    pendingDeleteNovel.value = null
    if (selectedNovel.value?.id === novel.id) {
      selectedNovel.value = null
      chapters.value = []
      chapterTotal.value = 0
      chapterHasMore.value = false
      currentPage.value = 'novels'
      stopPolling()
    }
    await refreshNovels()
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '删除失败')
  } finally {
    deletingNovel.value = false
    globalLoading.value = false
  }
}

const viewChapter = async (chapter) => {
  if (isChapterProcessing(chapter)) {
    ElMessage.warning('当前正在解析，暂时不能打开章节阅读')
    return
  }
  resetReaderState()
  await loadChapterForReader(chapter, false)
}

const resetReaderState = () => {
  selectedChapter.value = null
  allDialogues.value = []
  chapterContent.value = ''
  originalChapters.value = []
  visibleMessageCount.value = 0
  nextChapterLoading.value = false
  prevChapterLoading.value = false
  readerEnded.value = false
  readerAtStart.value = false
  loadedChapterIds.value = new Set()
  loadedChapterMeta.value = new Map()
  firstLoadedChapter.value = null
  lastLoadedChapter.value = null
  prevOriginalLoading.value = false
  nextOriginalLoading.value = false
  originalAtStart.value = false
  originalAtEnd.value = false
  loadedOriginalChapterIds.value = new Set()
  firstOriginalChapter.value = null
  lastOriginalChapter.value = null
}

const loadChapterForReader = async (chapter, append) => {
  selectedChapter.value = chapter
  loadedChapterMeta.value.set(chapter.id, chapter)
  currentPage.value = 'content'
  contentTab.value = chapter.is_processed ? 'dialogue' : 'original'

  try {
    const detailRes = await axios.get(`/api/chapter/${chapter.id}`)
    chapterContent.value = detailRes.data.content || ''
    if (!append) {
      originalChapters.value = [detailRes.data]
      loadedOriginalChapterIds.value = new Set([chapter.id])
      firstOriginalChapter.value = chapter
      lastOriginalChapter.value = chapter
      originalAtStart.value = false
      originalAtEnd.value = false
    }

    if (chapter.is_processed) {
      const dialogueRes = await axios.get(`/api/chapter/${chapter.id}/dialogues`)
      const chapterItems = [
        {
          id: `chapter-${chapter.id}`,
          type: 'chapter',
          character: '章节',
          text: `${chapter.chapter_number}. ${chapter.title}`,
        },
        ...dialogueRes.data.map((item) => ({
          ...item,
          id: `${chapter.id}-${item.id}`,
          type: 'dialogue',
        })),
      ]

      if (append) {
        allDialogues.value = [...allDialogues.value, ...chapterItems]
        if (restoringReaderSnapshot.value) {
          visibleMessageCount.value = Math.min(allDialogues.value.length, visibleMessageCount.value)
        } else if (dialogueRevealMode.value === 'tap') {
          visibleMessageCount.value = Math.min(allDialogues.value.length, visibleMessageCount.value)
        } else {
          visibleMessageCount.value = Math.min(allDialogues.value.length, visibleMessageCount.value + messageBatchSize)
        }
        lastLoadedChapter.value = chapter
      } else {
        allDialogues.value = chapterItems
        visibleMessageCount.value = Math.min(
          restoringReaderSnapshot.value ? allDialogues.value.length : (dialogueRevealMode.value === 'tap' ? tapRevealInitialCount : messageBatchSize),
          allDialogues.value.length,
        )
        readerEnded.value = false
        readerAtStart.value = false
        loadedChapterIds.value = new Set()
        firstLoadedChapter.value = chapter
        lastLoadedChapter.value = chapter
        window.scrollTo({ top: 0, behavior: 'auto' })
      }
      loadedChapterIds.value.add(chapter.id)
      if (!append && !restoringReaderSnapshot.value) {
        await nextTick()
        if (chatWindowRef.value) {
          await loadPrevProcessedChapter(chatWindowRef.value)
          await fillChatViewport()
        }
      }
    } else {
      allDialogues.value = []
      visibleMessageCount.value = 0
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '获取章节内容失败')
  }
}

const getReadingProgress = () => {
  try {
    const key = `${readingProgressKeyBase}_${currentUser.value?.id || 'guest'}`
    return JSON.parse(localStorage.getItem(key) || '{}')
  } catch (error) {
    return {}
  }
}

const saveReadingProgress = () => {
  if (!selectedNovel.value?.id || !selectedChapter.value?.id || currentPage.value !== 'content' || restoringProgress.value) return
  const progress = getReadingProgress()
  const scrollTarget = contentTab.value === 'dialogue' ? chatWindowRef.value : originalWindowRef.value
  progress[selectedNovel.value.id] = {
    chapterId: selectedChapter.value.id,
    mode: contentTab.value,
    dialogueRevealMode: dialogueRevealMode.value,
    scrollTop: scrollTarget?.scrollTop || 0,
    visibleMessageCount: visibleMessageCount.value,
    dialogueFirstChapterId: firstLoadedChapter.value?.id || null,
    dialogueLastChapterId: lastLoadedChapter.value?.id || null,
    originalFirstChapterId: firstOriginalChapter.value?.id || null,
    originalLastChapterId: lastOriginalChapter.value?.id || null,
    updatedAt: Date.now(),
  }
  const key = `${readingProgressKeyBase}_${currentUser.value?.id || 'guest'}`
  localStorage.setItem(key, JSON.stringify(progress))
}

const restoreReadingProgress = async (novelId) => {
  const progress = getReadingProgress()[novelId]
  if (!progress?.chapterId) return

  restoringProgress.value = true
  restoringReaderSnapshot.value = true
  try {
    dialogueRevealMode.value = progress.dialogueRevealMode || 'scroll'
    const detailRes = await axios.get(`/api/chapter/${progress.chapterId}`)
    await loadChapterForReader(detailRes.data, false)
    contentTab.value = progress.mode || 'dialogue'
    if (contentTab.value === 'dialogue' && detailRes.data.is_processed) {
      await restoreDialogueSnapshot(progress)
      visibleMessageCount.value = Math.min(progress.visibleMessageCount || allDialogues.value.length, allDialogues.value.length)
    }
    if (contentTab.value === 'original') {
      await restoreOriginalSnapshot(progress)
    }
    await nextTick()
    const scrollTarget = contentTab.value === 'dialogue' ? chatWindowRef.value : originalWindowRef.value
    if (scrollTarget) {
      scrollTarget.scrollTop = Math.max(0, progress.scrollTop || 0)
      await waitForNextFrame()
      scrollTarget.scrollTop = Math.max(0, progress.scrollTop || 0)
    }
  } catch (error) {
    // 阅读记录失效时忽略，仍停留在章节列表。
  } finally {
    restoringReaderSnapshot.value = false
    restoringProgress.value = false
  }
}

const goBack = () => {
  saveReadingProgress()
  if (currentPage.value === 'content') {
    currentPage.value = 'chapters'
    return
  }
  if (currentPage.value === 'chapters') {
    currentPage.value = 'novels'
  }
}

const restoreDialogueSnapshot = async (progress) => {
  const targetFirstId = progress.dialogueFirstChapterId || firstLoadedChapter.value?.id
  const targetLastId = progress.dialogueLastChapterId || lastLoadedChapter.value?.id

  let guard = 0
  while (firstLoadedChapter.value?.id && targetFirstId && firstLoadedChapter.value.id !== targetFirstId && guard < 80) {
    const beforeId = firstLoadedChapter.value.id
    await loadPrevProcessedChapter(null, { restoring: true })
    if (firstLoadedChapter.value?.id === beforeId) break
    guard += 1
  }

  guard = 0
  while (lastLoadedChapter.value?.id && targetLastId && lastLoadedChapter.value.id !== targetLastId && guard < 80) {
    const beforeId = lastLoadedChapter.value.id
    await loadNextProcessedChapter({ restoring: true })
    if (lastLoadedChapter.value?.id === beforeId) break
    guard += 1
  }
}

const restoreOriginalSnapshot = async (progress) => {
  const targetFirstId = progress.originalFirstChapterId || firstOriginalChapter.value?.id
  const targetLastId = progress.originalLastChapterId || lastOriginalChapter.value?.id

  let guard = 0
  while (firstOriginalChapter.value?.id && targetFirstId && firstOriginalChapter.value.id !== targetFirstId && guard < 80) {
    const beforeId = firstOriginalChapter.value.id
    await loadPrevOriginalChapter(null, { restoring: true })
    if (firstOriginalChapter.value?.id === beforeId) break
    guard += 1
  }

  guard = 0
  while (lastOriginalChapter.value?.id && targetLastId && lastOriginalChapter.value.id !== targetLastId && guard < 80) {
    const beforeId = lastOriginalChapter.value.id
    await loadNextOriginalChapter({ restoring: true })
    if (lastOriginalChapter.value?.id === beforeId) break
    guard += 1
  }
}

const handleFileChange = (file) => {
  uploadFile.value = file.raw
}

const openUploadDialog = () => {
  resetUploadState()
  showUploadDialog.value = true
}

const resetUploadState = () => {
  uploadFile.value = null
  uploadRef.value?.clearFiles?.()
}

const uploadNovel = async () => {
  if (!uploadFile.value) {
    ElMessage.warning('请先选择 txt 文件')
    return
  }

  const formData = new FormData()
  formData.append('file', uploadFile.value)

  uploading.value = true
  showUploadDialog.value = false
  globalLoadingText.value = '正在上传小说...'
  globalLoading.value = true
  try {
    await axios.post('/api/upload', formData)
    globalLoading.value = false
    ElMessage.success('上传成功，请进入书籍后手动拆分章节')
    uploadFile.value = null
    await refreshNovels()
  } catch (error) {
    showUploadDialog.value = true
    ElMessage.error(error.response?.data?.error || '上传失败')
  } finally {
    uploading.value = false
    globalLoading.value = false
  }
}

const splitNovel = async () => {
  if (!selectedNovel.value) return
  splitting.value = true
  try {
    const res = await axios.post(`/api/split/${selectedNovel.value.id}`)
    ElMessage.success(res.data.message)
    await refreshNovels()
    await fetchChapters()
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '拆分失败')
  } finally {
    splitting.value = false
  }
}

const jumpToChapter = async () => {
  if (!selectedNovel.value?.id) return
  const total = selectedNovel.value.total_chapters || 1
  const targetChapterNumber = Math.min(Math.max(1, jumpChapterNumber.value || 1), total)
  jumpChapterNumber.value = targetChapterNumber
  try {
    const targetPage = Math.max(1, Math.ceil(targetChapterNumber / chapterPageSize.value))
    chapterPage.value = targetPage
    await fetchChapters()
    await nextTick()
    const chapterEl = document.querySelector(`[data-chapter-number="${targetChapterNumber}"]`)
    if (chapterEl) {
      chapterEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '跳转章节失败')
  }
}

const setDialogueRevealMode = async (mode) => {
  dialogueRevealMode.value = mode
  showReaderQuickPanel.value = false

  if (contentTab.value !== 'dialogue') return

  if (mode === 'tap') {
    visibleMessageCount.value = Math.min(allDialogues.value.length, Math.max(visibleMessageCount.value, tapRevealInitialCount))
    await nextTick()
    if (chatWindowRef.value) {
      await scrollChatToRevealPosition()
    }
  } else {
    await fillChatViewport()
  }

  saveReadingProgress()
}

const openReaderQuickPanel = () => {
  if (currentPage.value !== 'content') return
  showReaderQuickPanel.value = true
}

const waitForNextFrame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()))

const scrollChatToRevealPosition = async () => {
  if (!chatWindowRef.value) return
  await waitForNextFrame()
  await waitForNextFrame()

  const target = chatWindowRef.value
  target.scrollTop = target.scrollHeight
  await waitForNextFrame()
  target.scrollTop = target.scrollHeight
}

const revealSingleMessage = async () => {
  if (visibleMessageCount.value < allDialogues.value.length) {
    visibleMessageCount.value += 1
    await nextTick()
    await scrollChatToRevealPosition()
    saveReadingProgress()
    return true
  }

  const beforeLength = allDialogues.value.length
  await loadNextProcessedChapter()
  if (allDialogues.value.length > beforeLength && visibleMessageCount.value < allDialogues.value.length) {
    visibleMessageCount.value += 1
    await nextTick()
    await scrollChatToRevealPosition()
    saveReadingProgress()
    return true
  }

  return false
}

const handleChatWindowClick = async () => {
  if (dialogueRevealMode.value === 'tap') {
    await revealSingleMessage()
    return
  }
  openReaderQuickPanel()
}

const switchReaderMode = async (mode) => {
  contentTab.value = mode
  showReaderQuickPanel.value = false
  await nextTick()
  saveReadingProgress()
}

const closeReaderToChapters = () => {
  showReaderQuickPanel.value = false
  goBack()
}

const jumpToChapterFromReader = async () => {
  showReaderQuickPanel.value = false
  saveReadingProgress()
  currentPage.value = 'chapters'
  await nextTick()
  await jumpToChapter()
}

const processSingleChapter = async (chapter) => {
  try {
    await axios.post(`/api/chapter/${chapter.id}/process`)
    ElMessage.success(chapter.is_processed ? '已开始重新解析该章节' : '已开始转换该章节')
    showProgressDialog.value = true
    startPolling()
  } catch (error) {
    ElMessage.error(error.response?.data?.error || (chapter.is_processed ? '重新解析失败' : '转换失败'))
  }
}

const openProcessDialog = () => {
  if (!selectedNovel.value?.total_chapters) {
    ElMessage.warning('请先拆分章节')
    return
  }
  showProcessDialog.value = true
}

const startBatchProcess = async () => {
  if (!selectedNovel.value) return
  showProcessDialog.value = false
  showProgressDialog.value = true
  processProgress.value = 0

  try {
    await axios.post(`/api/process/${selectedNovel.value.id}`, {
      start_chapter: processConfig.value.startChapter,
      end_chapter: processConfig.value.endChapter,
    })
    startPolling()
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '启动解析失败')
    showProgressDialog.value = false
  }
}

const cancelProcess = async () => {
  if (!selectedNovel.value) return
  try {
    const res = await axios.post(`/api/process/${selectedNovel.value.id}/cancel`)
    ElMessage.success(res.data.message || '已取消')
    await checkProgress()
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '取消失败')
  }
}

const hideProgressDialog = () => {
  showProgressDialog.value = false
}

const startPolling = () => {
  if (!selectedNovel.value || polling.value) return
  polling.value = true
  checkProgress()
  progressTimer.value = setInterval(checkProgress, 5000)
}

const stopPolling = () => {
  polling.value = false
  if (progressTimer.value) {
    clearInterval(progressTimer.value)
    progressTimer.value = null
  }
}

const syncProcessStatus = async () => {
  if (!selectedNovel.value?.id) return
  try {
    const res = await axios.get(`/api/process/status/${selectedNovel.value.id}`)
    selectedNovel.value = { ...selectedNovel.value, ...res.data }
    processProgress.value = res.data.progress
    processedCount.value = res.data.task_total_chapters ? res.data.task_processed_chapters : res.data.processed_chapters
    totalCount.value = res.data.task_total_chapters || res.data.total_chapters
    processingRange.value = {
      start: res.data.task_start_chapter || null,
      end: res.data.task_end_chapter || res.data.task_start_chapter || null,
    }
  } catch (error) {
    // 进入书籍时状态同步失败不阻塞章节展示。
  }
}

const checkProgress = async () => {
  if (!selectedNovel.value) {
    stopPolling()
    return
  }

  try {
    const res = await axios.get(`/api/process/status/${selectedNovel.value.id}`)
    const oldProcessed = selectedNovel.value.processed_chapters || 0
    const oldTaskProcessed = selectedNovel.value.task_processed_chapters || 0
    const oldStatus = selectedNovel.value.status
    selectedNovel.value = { ...selectedNovel.value, ...res.data }
    processProgress.value = res.data.progress
    processedCount.value = res.data.task_total_chapters ? res.data.task_processed_chapters : res.data.processed_chapters
    totalCount.value = res.data.task_total_chapters || res.data.total_chapters
    processingRange.value = {
      start: res.data.task_start_chapter || null,
      end: res.data.task_end_chapter || res.data.task_start_chapter || null,
    }

    if (
      currentPage.value === 'chapters' &&
      (
        oldProcessed !== res.data.processed_chapters ||
        oldTaskProcessed !== (res.data.task_processed_chapters || 0) ||
        oldStatus !== res.data.status
      )
    ) {
      await fetchChapters()
    }

    if (['completed', 'split', 'failed', 'cancelled'].includes(res.data.status)) {
      stopPolling()
      processingRange.value = { start: null, end: null }
      await refreshNovels()
      if (currentPage.value === 'chapters') {
        chapterPage.value = 1
        await fetchChapters()
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }
      if (res.data.status === 'failed') {
        ElMessage.error('解析中断，请检查后端日志或大模型返回内容')
      } else if (res.data.status === 'cancelled') {
        ElMessage.warning('解析已取消')
      } else {
        ElMessage.success('解析任务已结束')
      }
    }
  } catch (error) {
    stopPolling()
  }
}

const isNarrator = (dialogue) => dialogue.character === '旁白'
const getAvatar = (name) => (name || '人').slice(0, 1)

const revealMoreMessages = () => {
  if (visibleMessageCount.value < allDialogues.value.length) {
    visibleMessageCount.value = Math.min(allDialogues.value.length, visibleMessageCount.value + messageBatchSize)
    return true
  }
  return false
}

const fillChatViewport = async () => {
  if (dialogueRevealMode.value === 'tap') return
  await nextTick()
  const target = chatWindowRef.value
  if (!target) return

  let guard = 0
  while (target.scrollHeight <= target.clientHeight + 20 && guard < 20) {
    const beforeLength = allDialogues.value.length
    const beforeVisible = visibleMessageCount.value

    if (!revealMoreMessages()) {
      await loadNextProcessedChapter()
    }

    await nextTick()
    if (beforeLength === allDialogues.value.length && beforeVisible === visibleMessageCount.value) {
      break
    }
    guard += 1
  }
}

const syncSelectedChapterFromChat = (scrollTarget) => {
  if (!scrollTarget) return
  const containerTop = scrollTarget.getBoundingClientRect().top
  const markers = Array.from(scrollTarget.querySelectorAll('.chapter-marker[data-message-id]'))
  if (!markers.length) return

  let currentMarker = markers[0]
  for (const marker of markers) {
    if (marker.getBoundingClientRect().top <= containerTop + 88) {
      currentMarker = marker
    } else {
      break
    }
  }

  const chapterId = Number(String(currentMarker.dataset.messageId || '').replace('chapter-', ''))
  if (!chapterId) return
  const chapter = loadedChapterMeta.value.get(chapterId)
  if (chapter && selectedChapter.value?.id !== chapter.id) {
    selectedChapter.value = chapter
  }
}

const syncSelectedChapterFromOriginal = (scrollTarget) => {
  if (!scrollTarget) return
  const containerTop = scrollTarget.getBoundingClientRect().top
  const sections = Array.from(scrollTarget.querySelectorAll('[data-original-id]'))
  if (!sections.length) return

  let currentSection = sections[0]
  for (const section of sections) {
    if (section.getBoundingClientRect().top <= containerTop + 88) {
      currentSection = section
    } else {
      break
    }
  }

  const chapterId = Number(currentSection.dataset.originalId || 0)
  if (!chapterId) return
  const chapter = loadedChapterMeta.value.get(chapterId)
  if (chapter && selectedChapter.value?.id !== chapter.id) {
    selectedChapter.value = chapter
  }
}

const handleChatScroll = async (event) => {
  syncSelectedChapterFromChat(event.target)
  if (!restoringProgress.value) saveReadingProgress()
  const target = event.target
  const nearTop = target.scrollTop <= 80
  const nearBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 80
  if (nearTop && !prevChapterLoading.value) {
    await loadPrevProcessedChapter(target)
    return
  }

  if (!nearBottom || nextChapterLoading.value) return
  if (dialogueRevealMode.value === 'tap') return

  if (revealMoreMessages()) return
  await loadNextProcessedChapter()
}

const handleWindowScroll = () => {
  if (currentPage.value === 'novels') {
    const nearBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 160
    if (nearBottom) {
      loadMoreNovels()
    }
    return
  }

  if (currentPage.value !== 'chapters') return
  const nearBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 160
  if (nearBottom) {
    loadMoreChapters()
  }
}

const changeFontSize = (delta) => {
  readerFontSize.value = Math.min(24, Math.max(13, readerFontSize.value + delta))
}

const loadNextProcessedChapter = async (options = {}) => {
  const restoring = !!options.restoring
  const baseChapter = lastLoadedChapter.value || selectedChapter.value
  if (!baseChapter || nextChapterLoading.value || readerEnded.value) return

  nextChapterLoading.value = true
    try {
      const res = await axios.get(`/api/chapter/${baseChapter.id}/next`, {
        params: { processed_only: 1 },
      })
      const nextChapter = res.data.chapter
      if (!nextChapter) {
        readerEnded.value = true
        return
      }
      if (loadedChapterIds.value.has(nextChapter.id)) return

      await loadChapterForReader(nextChapter, true)
    if (!restoring) {
      selectedChapter.value = nextChapter
      await nextTick()
      await fillChatViewport()
      saveReadingProgress()
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '自动加载下一章失败')
  } finally {
    nextChapterLoading.value = false
  }
}

const loadPrevProcessedChapter = async (scrollTarget, options = {}) => {
  const restoring = !!options.restoring
  const baseChapter = firstLoadedChapter.value || selectedChapter.value
  if (!baseChapter || prevChapterLoading.value || readerAtStart.value) return

  prevChapterLoading.value = true
  const anchor = getScrollAnchor(scrollTarget)

    try {
      const res = await axios.get(`/api/chapter/${baseChapter.id}/prev`, {
        params: { processed_only: 1 },
      })
      const prevChapter = res.data.chapter
      if (!prevChapter) {
        readerAtStart.value = true
        return
      }
      if (loadedChapterIds.value.has(prevChapter.id)) return

      const dialogueRes = await axios.get(`/api/chapter/${prevChapter.id}/dialogues`)
    const prevItems = [
      {
        id: `chapter-${prevChapter.id}`,
        type: 'chapter',
        character: '章节',
        text: `${prevChapter.chapter_number}. ${prevChapter.title}`,
      },
      ...dialogueRes.data.map((item) => ({
        ...item,
        id: `${prevChapter.id}-${item.id}`,
        type: 'dialogue',
      })),
    ]

    allDialogues.value = [...prevItems, ...allDialogues.value]
    visibleMessageCount.value = Math.min(allDialogues.value.length, visibleMessageCount.value + prevItems.length)
    loadedChapterIds.value.add(prevChapter.id)
    loadedChapterMeta.value.set(prevChapter.id, prevChapter)
    firstLoadedChapter.value = prevChapter

    if (!restoring) {
      await nextTick()
      restoreScrollAnchor(scrollTarget, anchor)
      saveReadingProgress()
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '加载上一章失败')
  } finally {
    prevChapterLoading.value = false
  }
}

const handleOriginalScroll = async (event) => {
  syncSelectedChapterFromOriginal(event.target)
  if (!restoringProgress.value) saveReadingProgress()
  const target = event.target
  const nearTop = target.scrollTop <= 80
  const nearBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 100

  if (nearTop) {
    await loadPrevOriginalChapter(target)
    return
  }
  if (nearBottom) {
    await loadNextOriginalChapter()
  }
}

const loadNextOriginalChapter = async (options = {}) => {
  const restoring = !!options.restoring
  const baseChapter = lastOriginalChapter.value || selectedChapter.value
  if (!baseChapter || nextOriginalLoading.value || originalAtEnd.value) return

  nextOriginalLoading.value = true
  try {
    const res = await axios.get(`/api/chapter/${baseChapter.id}/next`, {
      params: { processed_only: 0 },
    })
    const nextChapter = res.data.chapter
    if (!nextChapter) {
      originalAtEnd.value = true
      return
    }
    if (loadedOriginalChapterIds.value.has(nextChapter.id)) return
    const detailRes = await axios.get(`/api/chapter/${nextChapter.id}`)
    originalChapters.value = [...originalChapters.value, detailRes.data]
    loadedOriginalChapterIds.value.add(nextChapter.id)
    loadedChapterMeta.value.set(nextChapter.id, detailRes.data)
    lastOriginalChapter.value = nextChapter
    if (!restoring) {
      selectedChapter.value = nextChapter
      saveReadingProgress()
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '加载下一章原文失败')
  } finally {
    nextOriginalLoading.value = false
  }
}

const loadPrevOriginalChapter = async (scrollTarget, options = {}) => {
  const restoring = !!options.restoring
  const baseChapter = firstOriginalChapter.value || selectedChapter.value
  if (!baseChapter || prevOriginalLoading.value || originalAtStart.value) return

  prevOriginalLoading.value = true
  const anchor = getOriginalScrollAnchor(scrollTarget)
  try {
    const res = await axios.get(`/api/chapter/${baseChapter.id}/prev`, {
      params: { processed_only: 0 },
    })
    const prevChapter = res.data.chapter
    if (!prevChapter) {
      originalAtStart.value = true
      return
    }
    if (loadedOriginalChapterIds.value.has(prevChapter.id)) return
    const detailRes = await axios.get(`/api/chapter/${prevChapter.id}`)
    originalChapters.value = [detailRes.data, ...originalChapters.value]
    loadedOriginalChapterIds.value.add(prevChapter.id)
    loadedChapterMeta.value.set(prevChapter.id, detailRes.data)
    firstOriginalChapter.value = prevChapter
    if (!restoring) {
      await nextTick()
      restoreOriginalScrollAnchor(scrollTarget, anchor)
      saveReadingProgress()
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '加载上一章原文失败')
  } finally {
    prevOriginalLoading.value = false
  }
}

const getOriginalScrollAnchor = (scrollTarget) => {
  if (!scrollTarget) return null
  const containerRect = scrollTarget.getBoundingClientRect()
  const items = Array.from(scrollTarget.querySelectorAll('[data-original-id]'))
  const anchorEl = items.find((item) => item.getBoundingClientRect().bottom >= containerRect.top + 8)
  if (!anchorEl) return null
  return {
    id: anchorEl.dataset.originalId,
    offset: anchorEl.getBoundingClientRect().top - containerRect.top,
  }
}

const restoreOriginalScrollAnchor = (scrollTarget, anchor) => {
  if (!scrollTarget || !anchor?.id) return
  const restore = () => {
    const anchorEl = scrollTarget.querySelector(`[data-original-id="${CSS.escape(anchor.id)}"]`)
    if (!anchorEl) return
    const containerRect = scrollTarget.getBoundingClientRect()
    const newOffset = anchorEl.getBoundingClientRect().top - containerRect.top
    scrollTarget.scrollTop += newOffset - anchor.offset
  }
  restore()
  requestAnimationFrame(restore)
}

const getScrollAnchor = (scrollTarget) => {
  if (!scrollTarget) return null
  const containerRect = scrollTarget.getBoundingClientRect()
  const items = Array.from(scrollTarget.querySelectorAll('[data-message-id]'))
  const anchorEl = items.find((item) => item.getBoundingClientRect().bottom >= containerRect.top + 8)
  if (!anchorEl) return null

  return {
    id: anchorEl.dataset.messageId,
    offset: anchorEl.getBoundingClientRect().top - containerRect.top,
  }
}

const restoreScrollAnchor = (scrollTarget, anchor) => {
  if (!scrollTarget || !anchor?.id) return

  const restore = () => {
    const anchorEl = scrollTarget.querySelector(`[data-message-id="${CSS.escape(anchor.id)}"]`)
    if (!anchorEl) return
    const containerRect = scrollTarget.getBoundingClientRect()
    const newOffset = anchorEl.getBoundingClientRect().top - containerRect.top
    scrollTarget.scrollTop += newOffset - anchor.offset
  }

  restore()
  requestAnimationFrame(restore)
}

const getStatusType = (status) => {
  const map = {
    uploaded: 'info',
    split: 'warning',
    processing: 'primary',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info',
  }
  return map[status] || 'info'
}

const getStatusText = (status) => {
  const map = {
    uploaded: '已上传',
    split: '已拆章',
    processing: '解析中',
    completed: '已完成',
    failed: '需重试',
    cancelled: '已取消',
  }
  return map[status] || status || '未知'
}

const persistReadingBeforeLeave = () => {
  saveReadingProgress()
}

onMounted(() => {
  hydrateCurrentUser().then((hasValidUser) => {
    if (hasValidUser) refreshNovels()
  })
  window.addEventListener('scroll', handleWindowScroll, { passive: true })
  window.addEventListener('beforeunload', persistReadingBeforeLeave)
  document.addEventListener('visibilitychange', persistReadingBeforeLeave)
})

onBeforeUnmount(() => {
  saveReadingProgress()
  stopPolling()
  window.removeEventListener('scroll', handleWindowScroll)
  window.removeEventListener('beforeunload', persistReadingBeforeLeave)
  document.removeEventListener('visibilitychange', persistReadingBeforeLeave)
})
</script>

<style scoped>
:global(body) {
  margin: 0;
  background: #eef3ef;
  font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
}

* {
  box-sizing: border-box;
}

.app-shell {
  min-height: 100vh;
  color: #182820;
  background:
    radial-gradient(circle at 100% 0%, rgba(150, 226, 105, 0.28), transparent 34%),
    linear-gradient(180deg, #f7faf7 0%, #e6eee8 100%);
}

.auth-page {
  min-height: 100vh;
  padding: 24px 14px;
  display: grid;
  place-items: center;
}

.auth-card {
  width: min(460px, 100%);
  display: grid;
  gap: 16px;
}

.auth-form-card {
  position: relative;
  overflow: hidden;
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  box-shadow: 0 22px 54px rgba(51, 86, 61, 0.18);
}

.auth-form-card {
  padding: 20px;
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(18px);
}

.auth-title {
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  text-align: center;
}

.auth-title strong {
  color: #244631;
  font-size: 22px;
  font-weight: 950;
}

.auth-title span {
  color: #708078;
  font-size: 13px;
}

.auth-tabs {
  padding: 4px;
  margin-bottom: 14px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-radius: 999px;
  background: rgba(36, 70, 49, 0.08);
}

.auth-tabs button,
.logout-btn {
  border: 0;
  cursor: pointer;
}

.auth-tabs button {
  height: 38px;
  border-radius: 999px;
  color: #557064;
  background: transparent;
  font-weight: 800;
}

.auth-tabs button.active {
  color: #163323;
  background: #ffffff;
  box-shadow: 0 8px 20px rgba(54, 93, 68, 0.14);
}

.auth-form :deep(.el-select) {
  width: 100%;
}

.remember-check {
  margin: -4px 0 14px;
}

.auth-model-tip {
  margin: 6px 0 14px;
  padding: 12px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(217, 247, 182, 0.62), rgba(255, 255, 255, 0.64));
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.auth-model-tip strong {
  color: #244631;
}

.auth-model-tip span {
  color: #708078;
  font-size: 12px;
  line-height: 1.5;
}

.auth-submit {
  width: 100%;
  height: 44px;
  margin-top: 4px;
  border-radius: 14px;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  height: 58px;
  padding: 8px 12px;
  display: grid;
  grid-template-columns: 112px 1fr 54px;
  align-items: center;
  background: rgba(248, 251, 248, 0.94);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(30, 49, 39, 0.08);
}

.sub-page-topbar {
  grid-template-columns: 42px 1fr 42px;
}

.left-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.back-btn,
.text-btn {
  border: 0;
  background: transparent;
  color: #1b3025;
}

.back-btn {
  width: 28px;
  padding: 0;
  font-size: 34px;
  line-height: 1;
}

.text-btn {
  font-size: 13px;
}

.logout-btn {
  justify-self: end;
  padding: 7px 10px;
  border-radius: 999px;
  color: #42604f;
  background: rgba(36, 70, 49, 0.08);
  font-size: 12px;
  font-weight: 800;
}

.top-brand {
  color: #244631;
  font-size: 14px;
  font-weight: 900;
  text-align: left;
  white-space: nowrap;
}

.title-block {
  min-width: 0;
  text-align: center;
  display: flex;
  flex-direction: column;
}

.title-block strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page {
  width: min(760px, 100%);
  margin: 0 auto;
  padding: 14px;
}

.home-page {
  padding: 12px 12px 30px;
}

.hero-card {
  position: relative;
  overflow: hidden;
  min-height: 148px;
  padding: 18px;
  border-radius: 24px;
  background:
    radial-gradient(circle at 92% 18%, rgba(255, 255, 255, 0.64), transparent 22%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.72), rgba(255, 255, 255, 0.18)),
    linear-gradient(135deg, #d5f6b0 0%, #85daa0 50%, #5fbe84 100%);
  box-shadow: 0 18px 42px rgba(59, 101, 73, 0.18);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 14px;
}

.hero-card p {
  margin: 0 0 6px;
  color: rgba(20, 43, 28, 0.7);
  font-weight: 800;
  letter-spacing: 1px;
}

.hero-card h1 {
  max-width: 310px;
  margin: 0 0 10px;
  font-size: 24px;
  line-height: 1.2;
}

.hero-card span {
  display: block;
  max-width: 300px;
  color: rgba(22, 48, 32, 0.72);
  font-size: 13px;
  line-height: 1.6;
}

.upload-book-btn,
.shelf-action {
  border: 0;
  border-radius: 999px;
  background: #17291f;
  color: #f7fff5;
  font-weight: 900;
  box-shadow: 0 10px 24px rgba(24, 45, 34, 0.2);
}

.upload-book-btn {
  align-self: flex-start;
  padding: 10px 15px;
  font-size: 14px;
}

.shelf-header {
  margin: 18px 0 10px;
  padding: 0 4px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.shelf-header strong {
  display: block;
  color: #172920;
  font-size: 19px;
  font-weight: 950;
}

.shelf-header span {
  display: block;
  margin-top: 3px;
  color: #7c8a82;
  font-size: 12px;
}

.shelf-action {
  padding: 7px 14px;
  font-size: 13px;
}

.shelf-actions {
  display: flex;
  gap: 8px;
}

.shelf-action.muted {
  background: rgba(255, 255, 255, 0.72);
  color: #244631;
  box-shadow: 0 6px 18px rgba(24, 45, 34, 0.08);
}

.section-title {
  margin: 20px 2px 10px;
  font-weight: 900;
}

.chapter-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.novel-list.shelf-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.novel-card,
.chapter-row,
.process-panel,
.hint-card {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(24, 45, 34, 0.08);
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(26, 45, 35, 0.07);
}

.novel-card {
  min-width: 0;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-radius: 20px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(249, 251, 246, 0.88)),
    #fff;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.novel-card:active {
  transform: translateY(2px) scale(0.99);
}

.book-cover {
  position: relative;
  overflow: hidden;
  aspect-ratio: 0.78;
  min-height: 142px;
  padding: 38px 12px 12px 20px;
  border-radius: 16px 11px 11px 16px;
  background:
    linear-gradient(90deg, rgba(0, 0, 0, 0.16), transparent 16%),
    radial-gradient(circle at 80% 8%, rgba(255, 255, 255, 0.48), transparent 28%),
    linear-gradient(145deg, #1f6f4a 0%, #63c784 58%, #d6f59b 100%);
  box-shadow:
    inset 7px 0 0 rgba(14, 51, 34, 0.28),
    inset -1px 0 0 rgba(255, 255, 255, 0.36),
    0 14px 24px rgba(27, 52, 36, 0.16);
  color: #fff;
}

.book-cover strong {
  position: relative;
  z-index: 2;
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  font-size: 16px;
  line-height: 1.28;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.22);
}

.book-badge {
  position: absolute;
  left: 19px;
  top: 12px;
  z-index: 2;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.22);
  color: rgba(255, 255, 255, 0.92);
  font-size: 11px;
  backdrop-filter: blur(8px);
}

.book-cover small {
  position: absolute;
  left: 20px;
  bottom: 12px;
  color: rgba(255, 255, 255, 0.78);
  font-size: 11px;
  font-weight: 700;
}

.book-spine {
  position: absolute;
  inset: 0 auto 0 0;
  width: 12px;
  background: rgba(15, 42, 28, 0.22);
}

.book-shine {
  position: absolute;
  top: -20%;
  right: 8%;
  width: 46px;
  height: 140%;
  transform: rotate(18deg);
  background: linear-gradient(180deg, transparent, rgba(255, 255, 255, 0.24), transparent);
}

.novel-main {
  min-width: 0;
  padding: 0 2px;
}

.novel-main h3,
.chapter-info h3 {
  margin: 0;
  font-size: 15px;
}

.novel-main h3 {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-main p,
.chapter-info p,
.novel-main span {
  margin: 6px 0 0;
  color: #7c8a82;
  font-size: 12px;
}

.book-progress {
  overflow: hidden;
  height: 6px;
  margin-top: 8px;
  border-radius: 999px;
  background: #e4ece5;
}

.book-progress i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #60c77b, #c9ed6d);
}

.novel-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  padding: 0 2px 2px;
  color: #7c8a82;
  font-size: 12px;
}

.delete-link {
  border: 0;
  background: transparent;
  color: #b45a4c;
  font-size: 12px;
}

.delete-confirm {
  padding: 4px 2px;
}

.delete-confirm strong {
  display: block;
  color: #172920;
  font-size: 18px;
  line-height: 1.5;
}

.delete-confirm p {
  margin: 10px 0 0;
  color: #6f7d74;
  font-size: 14px;
  line-height: 1.7;
}

.glass-loading {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: grid;
  place-items: center;
  background: rgba(235, 242, 236, 0.5);
  backdrop-filter: blur(14px);
}

.glass-loading-card {
  min-width: 172px;
  padding: 22px 24px;
  border-radius: 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 13px;
  color: #17331b;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 52px rgba(26, 45, 35, 0.18);
}

.glass-loading-card strong {
  font-size: 14px;
}

.process-panel {
  padding: 16px;
  margin-bottom: 10px;
}

.process-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.process-head span {
  color: #7c8a82;
  font-size: 12px;
}

.process-head strong {
  display: block;
  margin-top: 4px;
  font-size: 28px;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.chapter-jump {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.chapter-jump :deep(.el-input-number) {
  width: 128px;
}

.hint-card {
  padding: 10px 12px;
  margin-bottom: 10px;
  color: #66746c;
  font-size: 13px;
  line-height: 1.6;
}

.chapter-row {
  min-height: 76px;
  padding: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.chapter-row.processing {
  opacity: 0.68;
  cursor: not-allowed;
}

.chapter-index {
  min-width: 44px;
  height: 36px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: #e0f5c4;
  color: #235126;
  font-size: 13px;
  font-weight: 900;
}

.chapter-info {
  flex: 1;
  min-width: 0;
}

.chapter-info h3 {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.list-loading {
  width: fit-content;
  margin: 16px auto 8px;
  padding: 8px 12px;
  border-radius: 999px;
  color: #6d7b72;
  background: rgba(255, 255, 255, 0.68);
  font-size: 13px;
}

.reader-page {
  min-height: calc(100vh - 58px);
  background: #e7ece8;
}

.reader-toolbar {
  position: sticky;
  top: 58px;
  z-index: 7;
  padding: 4px 14px 8px;
  background: transparent;
  pointer-events: none;
}

.reader-toolbar-toggle {
  width: 46px;
  height: 24px;
  border: 0;
  border-radius: 999px;
  padding: 0;
  display: grid;
  place-items: center;
  margin: 0 auto;
  background:
    radial-gradient(circle at 50% -20%, rgba(255, 255, 255, 0.8), transparent 46%),
    rgba(224, 245, 196, 0.42);
  color: rgba(36, 70, 49, 0.72);
  font-weight: 900;
  box-shadow: 0 5px 16px rgba(26, 45, 35, 0.06);
  backdrop-filter: blur(10px);
  pointer-events: auto;
}

.reader-toolbar-toggle span {
  width: 12px;
  height: 12px;
  border-right: 2px solid rgba(36, 70, 49, 0.68);
  border-bottom: 2px solid rgba(36, 70, 49, 0.68);
  transform: translateY(-3px) rotate(45deg);
  transition: transform 0.18s ease;
}

.reader-toolbar.expanded .reader-toolbar-toggle span {
  transform: translateY(3px) rotate(225deg);
}

.reader-toolbar-body {
  margin-top: 6px;
  padding-top: 9px;
  padding: 10px;
  border-radius: 18px;
  background: rgba(231, 236, 232, 0.92);
  backdrop-filter: blur(12px);
  box-shadow: 0 10px 28px rgba(26, 45, 35, 0.1);
  animation: toolbarDrop 0.2s ease both;
  pointer-events: auto;
}

.font-tools {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  color: #596960;
  font-size: 13px;
}

.font-tools button {
  border: 0;
  border-radius: 999px;
  padding: 5px 10px;
  background: #ffffff;
  color: #244631;
  font-weight: 900;
  box-shadow: 0 4px 12px rgba(26, 45, 35, 0.08);
}

.font-tools strong {
  min-width: 26px;
  text-align: center;
  color: #244631;
}

.reader-tabs {
  padding-top: 9px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.reader-tabs button {
  border: 0;
  border-radius: 999px;
  padding: 10px;
  background: #d6ddd8;
  color: #52635a;
  font-weight: 800;
}

.reader-tabs button.active {
  background: #9ee86d;
  color: #17331b;
}

.dialogue-mode-switch {
  padding-top: 9px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.dialogue-mode-switch button {
  border: 0;
  border-radius: 999px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.82);
  color: #52635a;
  font-weight: 800;
  box-shadow: 0 6px 16px rgba(34, 55, 41, 0.06);
}

.dialogue-mode-switch button.active {
  background: linear-gradient(135deg, #dff8be, #9ee86d);
  color: #17331b;
}

.chat-window {
  width: min(760px, 100%);
  height: calc(100vh - 112px);
  margin: 0 auto;
  padding: 8px 14px 26px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.chat-window.tap-reveal-mode {
  position: relative;
  padding-top: 56px;
  padding-bottom: 118px;
}

.reader-toolbar.expanded + .chat-window {
  height: calc(100vh - 190px);
}

.message-item {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  margin: 13px 0;
}

.message-item.narrator {
  justify-content: center;
}

.message-item.chapter-marker {
  justify-content: center;
  margin: 18px 0;
}

.pop-message {
  animation: messagePop 0.34s cubic-bezier(0.2, 0.86, 0.2, 1.12) both;
}

.avatar {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  color: #fff;
  font-weight: 900;
  background: linear-gradient(135deg, #20b15a, #6bd46b);
}

.bubble {
  max-width: 78%;
  padding: 9px 11px 11px;
  border-radius: 5px 15px 15px;
  background: #fff;
  box-shadow: 0 5px 16px rgba(37, 52, 43, 0.08);
}

.speaker {
  margin-bottom: 5px;
  color: #728076;
  font-size: 12px;
}

.message-text {
  color: #182820;
  font-size: var(--reader-font-size);
  line-height: var(--reader-line-height);
  white-space: pre-wrap;
}

.narrator-bubble {
  max-width: 92%;
  padding: 10px 13px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.64);
  border: 1px dashed rgba(86, 111, 96, 0.26);
  color: #53635a;
  font-size: calc(var(--reader-font-size) - 1px);
  line-height: var(--reader-line-height);
  white-space: pre-wrap;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.34);
}

.chapter-divider {
  padding: 8px 13px;
  border-radius: 999px;
  color: #2f5d38;
  background: linear-gradient(135deg, #e3f8c6, #f5fff0);
  border: 1px solid rgba(94, 158, 85, 0.22);
  font-size: 13px;
  font-weight: 800;
}

.reader-loading,
.reader-ending {
  margin: 16px auto 0;
  width: fit-content;
  padding: 8px 12px;
  border-radius: 999px;
  color: #6f7d74;
  background: rgba(255, 255, 255, 0.62);
  font-size: 13px;
}

.reader-quick-mask {
  position: fixed;
  inset: 0;
  z-index: 25;
  padding: 22px;
  display: grid;
  place-items: center;
  background: rgba(231, 236, 232, 0.18);
  backdrop-filter: blur(14px);
}

.reader-quick-panel {
  width: min(360px, 100%);
  padding: 20px 18px 18px;
  border-radius: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.82);
  box-shadow: 0 22px 54px rgba(26, 45, 35, 0.18);
}

.reader-quick-panel > strong {
  color: #17331b;
  font-size: 18px;
  line-height: 1.5;
  text-align: center;
}

.reader-quick-panel > span {
  color: #718178;
  font-size: 13px;
  text-align: center;
}

.reader-quick-actions,
.reader-quick-font,
.reader-quick-jump {
  display: flex;
  align-items: center;
  gap: 8px;
}

.reader-quick-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
}

.reader-quick-submodes {
  margin-top: -2px;
}

.reader-quick-actions button,
.reader-quick-font button,
.reader-quick-jump button,
.reader-quick-back {
  border: 0;
  border-radius: 14px;
  background: #edf3ee;
  color: #244631;
  font-weight: 800;
}

.reader-quick-actions button {
  height: 40px;
}

.reader-quick-actions button.active {
  background: linear-gradient(135deg, #dff8be, #9ee86d);
  color: #17331b;
}

.reader-quick-font {
  justify-content: center;
}

.reader-quick-font button {
  min-width: 48px;
  height: 38px;
}

.reader-quick-font strong {
  min-width: 28px;
  text-align: center;
  color: #244631;
}

.reader-quick-jump :deep(.el-input-number) {
  flex: 1;
}

.reader-quick-jump button,
.reader-quick-back {
  height: 40px;
  padding: 0 14px;
}

.reader-quick-back {
  background: #17291f;
  color: #f7fff5;
}

.original-content {
  width: min(760px, calc(100% - 28px));
  height: calc(100vh - 112px);
  margin: 0 auto 24px;
  padding: 18px;
  border-radius: 18px;
  background: #fffdf7;
  color: #2c2b25;
  font-size: calc(var(--reader-font-size) + 2px);
  line-height: calc(var(--reader-line-height) + 0.12);
  white-space: pre-wrap;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.reader-toolbar.expanded ~ .original-content {
  height: calc(100vh - 190px);
}

.original-chapter + .original-chapter {
  margin-top: 26px;
  padding-top: 18px;
  border-top: 1px dashed rgba(80, 100, 88, 0.18);
}

.original-title {
  margin: 0 0 14px;
  color: #244631;
  font-size: 18px;
  line-height: 1.5;
  text-align: center;
}

.original-body {
  white-space: pre-wrap;
}

.upload-panel {
  margin-top: -8px;
  padding: 8px 2px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
}

.upload-book-visual {
  position: relative;
  overflow: hidden;
  width: 64px;
  height: 86px;
  padding-left: 14px;
  border-radius: 14px 9px 9px 14px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  color: #fff;
  background:
    linear-gradient(90deg, rgba(0, 0, 0, 0.18), transparent 20%),
    linear-gradient(145deg, #1f6f4a, #8bd68d);
  box-shadow: 0 12px 26px rgba(27, 52, 36, 0.16);
}

.upload-book-visual strong {
  position: relative;
  z-index: 2;
  font-size: 18px;
}

.upload-panel-copy {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.upload-panel-copy strong {
  color: #172920;
  font-size: 19px;
}

.upload-panel-copy span {
  color: #718178;
  font-size: 13px;
  line-height: 1.6;
}

.model-panel {
  padding-bottom: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.model-panel strong {
  color: #172920;
  font-size: 19px;
}

.model-panel span {
  color: #718178;
  font-size: 13px;
  line-height: 1.6;
}

.model-form :deep(.el-select) {
  width: 100%;
}

.upload-copy {
  padding: 28px 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: #53645b;
}

.shelf-upload :deep(.el-upload-dragger) {
  border-radius: 22px;
  border: 1px dashed rgba(36, 70, 49, 0.28);
  background:
    radial-gradient(circle at 100% 0%, rgba(150, 226, 105, 0.18), transparent 34%),
    rgba(255, 255, 255, 0.7);
}

.dialog-tip,
.loading-card p {
  color: #7b8a82;
  font-size: 13px;
  line-height: 1.6;
}

.loading-card {
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.spinner {
  width: 54px;
  height: 54px;
  margin: 0 auto;
  border-radius: 50%;
  border: 5px solid #dfe7e1;
  border-top-color: #57c84d;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes messagePop {
  from {
    opacity: 0;
    transform: translateY(16px) scale(0.97);
    filter: blur(2px);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
    filter: blur(0);
  }
}

@keyframes toolbarDrop {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (min-width: 768px) {
  .topbar {
    padding-left: calc((100% - 760px) / 2 + 12px);
    padding-right: calc((100% - 760px) / 2 + 12px);
  }
}

@media (max-width: 380px) {
  .page {
    padding: 12px 10px;
  }

  .novel-list.shelf-grid {
    gap: 9px;
  }

  .novel-card {
    padding: 8px;
    border-radius: 18px;
  }

  .book-cover {
    min-height: 132px;
    padding: 35px 9px 10px 17px;
  }

  .book-cover strong {
    font-size: 14px;
  }

  .book-badge {
    left: 17px;
    top: 10px;
    font-size: 11px;
  }

  .book-cover small {
    left: 17px;
    bottom: 10px;
    font-size: 10px;
  }

  .novel-main h3 {
    font-size: 13px;
  }

  .novel-main p,
  .novel-actions,
  .delete-link {
    font-size: 11px;
  }
}
</style>
