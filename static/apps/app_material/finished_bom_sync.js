/* 成品 BOM 与 SAP BOM 的占比对比。不落库。

   本地签名：SAP 编码 → 份数占合计的百分比。缺编码的主 BOM 行使该版本不能标已同步；
   色粉缺编码只让「主 BOM + 色粉」这个签名作废，仅主 BOM 仍可对比。
   SAP 侧先折成千克：KG 原样，G 除以 1000。单位 PC 的行忽略。其它单位整张不参与匹配。
   同一编码先加总。占比收到 6 位小数后必须相同。

   例：60 份 + 40 份，对上 600000 G + 400000 G，也对上 600 KG + 400 KG。
   单位是 TO 的整张 BOM 不标已同步。
*/
function shareMap(pairs) {
    const totals = new Map()
    let sum = 0
    pairs.forEach(([code, qty]) => {
        if (!code || !(qty > 0)) return
        totals.set(code, (totals.get(code) || 0) + qty)
        sum += qty
    })
    if (!(sum > 0)) return null
    const shares = new Map()
    totals.forEach((qty, code) => shares.set(code, qty / sum * 100))
    return shares
}

function sameShares(left, right) {
    if (!left || !right || left.size !== right.size || left.size === 0) return false
    for (const [code, share] of left) {
        if (!right.has(code)) return false
        if (round6(share) !== round6(right.get(code))) return false
    }
    return true
}

function localSignature(lines) {
    if (lines.some(line => line.missing_sap_code)) return null
    return shareMap(lines.map(line => [line.warehouse_code, Number(line.percentage)]))
}

function sapKg(item) {
    const unit = String(item.meins || "").trim().toUpperCase()
    const qty = Number(item.menge)
    if (!Number.isFinite(qty)) return null
    if (unit === "KG") return qty
    if (unit === "G") return qty / 1000
    return null
}

function packQty(value) {
    const number = Number(value)
    if (!Number.isFinite(number)) return ""
    return round3(number).toFixed(3).replace(/0+$/, "").replace(/\.$/, "")
}

function byStlal(left, right) {
    return String(left.stlal).localeCompare(String(right.stlal), undefined, { numeric: true })
}

function packagingBags(items) {
    const bags = []
    for (const item of items || []) {
        if (String(item.meins || "").trim().toUpperCase() !== "PC") continue
        const code = String(item.idnrk || "").trim()
        if (!code) continue
        bags.push({ code, qty: packQty(item.menge) })
    }
    return bags
}

function sapSignature(items) {
    const pairs = []
    for (const item of items) {
        const unit = String(item.meins || "").trim().toUpperCase()
        if (unit === "PC") continue
        const qty = sapKg(item)
        if (qty === null) return { unsupported: true, shares: null }
        pairs.push([String(item.idnrk || "").trim(), qty])
    }
    return { unsupported: false, shares: shareMap(pairs) }
}

function classify(version, sapShares) {
    const main = localSignature(version.main_lines)
    if (!main) return null
    const colorUsable = version.has_color_bom
        && version.color_lines.length > 0
        && !version.color_lines.some(line => line.missing_sap_code)
    const merged = colorUsable
        ? localSignature(version.main_lines.concat(version.color_lines))
        : null
    const mainHit = sameShares(main, sapShares)
    const mergedHit = !!(merged && sameShares(merged, sapShares) && !sameShares(main, merged))
    if (mergedHit) return "merged"
    if (mainHit) return "main"
    if (merged && sameShares(merged, sapShares)) return "merged"
    return null
}

function round3(value) {
    const negative = value < 0
    const rounded = Math.round(Math.abs(value) * 1000) / 1000
    return negative ? -rounded : rounded
}

function round6(value) {
    const negative = value < 0
    const rounded = Math.round(Math.abs(value) * 1000000) / 1000000
    return negative ? -rounded : rounded
}

function format3(value) {
    return round3(value).toFixed(3)
}

function previewLines(main, color, merge, bmeng) {
    const source = merge ? main.concat(color) : main.slice()
    const buckets = []
    const index = new Map()
    source.forEach(line => {
        const code = (line.warehouse_code || "").trim()
        if (!code) return
        if (!index.has(code)) {
            index.set(code, buckets.length)
            buckets.push({
                code,
                name: line.name,
                modelName: line.model_name,
                percentage: 0,
            })
        }
        buckets[index.get(code)].percentage += Number(line.percentage)
    })
    const base = Number(bmeng)
    return buckets.map((row, i) => ({
        posnr: String((i + 1) * 10).padStart(4, "0"),
        idnrk: row.code,
        name: row.name,
        model_name: row.modelName || "",
        menge: format3(row.percentage / 100 * base * 1000),
        meins: "G",
    }))
}

function missingNames(main, color, merge) {
    const source = merge ? main.concat(color) : main
    const names = []
    const seen = new Set()
    source.forEach(line => {
        if ((line.warehouse_code || "").trim() || seen.has(line.name)) return
        seen.add(line.name)
        names.push(line.name)
    })
    return names
}

function csrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)
    return match ? decodeURIComponent(match[1]) : ""
}

async function api(url, options = {}) {
    const headers = {
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
        ...(options.body ? { "Content-Type": "application/json" } : {}),
    }
    const response = await fetch(url, { credentials: "same-origin", ...options, headers })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
        const error = new Error(data.detail || "请求失败")
        error.payload = data
        error.status = response.status
        throw error
    }
    return data
}

function today() {
    const now = new Date()
    const month = String(now.getMonth() + 1).padStart(2, "0")
    const day = String(now.getDate()).padStart(2, "0")
    return `${now.getFullYear()}-${month}-${day}`
}

function sapKey(werks, stlan, stlal) {
    return `${werks}|${stlan}|${stlal}`
}

async function readAlt(matnr, werks, stlan, stlal, datuv) {
    const alt = {
        key: sapKey(werks, stlan, stlal),
        werks,
        stlan,
        stlal,
        items: [],
        error: "",
        unsupported: false,
        shares: null,
    }
    try {
        const detail = await api(
            `/api/sap/boms/${encodeURIComponent(matnr)}/${encodeURIComponent(werks)}/${encodeURIComponent(stlan)}/${encodeURIComponent(stlal)}/?datuv=${encodeURIComponent(datuv)}`,
        )
        alt.items = detail.items || []
        const signature = sapSignature(alt.items)
        alt.unsupported = signature.unsupported
        alt.shares = signature.shares
    } catch (error) {
        alt.error = error.message
    }
    return alt
}

function initialSapCode() {
    const injected = window.__FINISHED_BOM_SAP_CODE__
    if (typeof injected === "string" && injected.trim()) return injected.trim()
    return (new URLSearchParams(window.location.search).get("sap_code") || "").trim()
}

const { createApp, ref, reactive, computed, watch, nextTick } = Vue

createApp({
    setup() {
        const sapCode = ref(initialSapCode())
        const plants = ref([])
        const selectedPlants = ref([])
        const headerDate = ref(today())
        const loading = ref(false)
        const loadText = ref("")
        const loadPercent = ref(0)
        const material = ref(null)
        const localTree = ref([])
        const sapTree = ref([])
        const treeKey = ref(0)
        const hitKey = ref("")
        const sapTreeRef = ref(null)

        const localOpen = ref(false)
        const current = ref(null)
        const form = reactive({
            werks: "",
            stlan: "1",
            stlal: "01",
            bmeng: 1000,
            datuv: today(),
            ausch: 1,
            stlst: "1",
            stktx: "",
            ztext: "",
            mergeColor: false,
            packagingCode: "",
            packagingName: "",
            packagingQty: null,
        })
        const packagingOpen = ref(false)
        const packagingQuery = reactive({ q: "", werks: "" })
        const packagingRows = ref([])
        const packagingLoading = ref(false)
        const checkResult = ref(null)
        const checking = ref(false)
        const saving = ref(false)

        const sapOpen = ref(false)
        const sapCurrent = ref(null)
        const deleting = ref(false)
        let loadedProjects = null
        let loadedDetails = []
        let loadedPlants = []

        watch(() => [form.werks, form.stlan, form.stlal], () => {
            checkResult.value = null
        })

        const missingNamesOfForm = computed(() => {
            if (!current.value) return []
            return missingNames(current.value.main_lines, current.value.color_lines, form.mergeColor)
        })
        const packagingLabel = computed(() => {
            if (!form.packagingCode) return ""
            return form.packagingName
                ? `${form.packagingCode} ${form.packagingName}`
                : form.packagingCode
        })
        const preview = computed(() => {
            if (!current.value) return []
            const rows = previewLines(
                current.value.main_lines,
                current.value.color_lines,
                form.mergeColor,
                form.bmeng,
            )
            const code = (form.packagingCode || "").trim()
            const qty = form.packagingQty
            if (!code || qty === null || qty === undefined || qty === "") return rows
            return rows.concat([{
                posnr: String((rows.length + 1) * 10).padStart(4, "0"),
                idnrk: code,
                name: form.packagingName || "",
                model_name: "",
                menge: format3(Number(qty)),
                meins: "PC",
            }])
        })

        function plantLabel(plant) {
            return plant.name ? `${plant.code} ${plant.name}` : plant.code
        }

        function packagingTitle(bags) {
            return (bags || []).map(bag => bag.qty ? `${bag.code} × ${bag.qty}` : bag.code).join("、")
        }

        function rowClass({ row }) {
            return row.missing_sap_code ? "row-missing" : ""
        }

        function buildLocalTree(projects, matches) {
            return projects.map(project => ({
                id: `p-${project.id}`,
                kind: "project",
                code: project.code,
                name: project.name,
                children: project.nodes.map(node => ({
                    id: node.unassigned ? `u-${project.id}` : `n-${node.id}`,
                    kind: "stage",
                    label: node.label,
                    children: node.formulas.map(formula => ({
                        id: `f-${project.id}-${node.id || "u"}-${formula.code}`,
                        kind: "formula",
                        code: formula.code,
                        name: formula.name,
                        children: formula.versions.map(version => {
                            const hits = matches.get(version.id) || []
                            const missingCode = version.main_lines.some(line => line.missing_sap_code)
                            return {
                                id: `v-${version.id}`,
                                kind: "version",
                                versionNo: version.version,
                                type: "version",
                                version,
                                synced: hits.length > 0,
                                mature: version.is_mature,
                                missingCode,
                                children: hits.slice().sort(byStlal).map(hit => ({
                                    id: `s-${version.id}-${hit.key}`,
                                    type: "sync",
                                    werks: hit.werks,
                                    stlan: hit.stlan,
                                    stlal: hit.stlal,
                                    matchKind: hit.kind,
                                    matchLabel: hit.kind === "merged" ? "主BOM+色粉" : "仅主BOM",
                                    packaging: hit.packaging,
                                    sapKey: hit.key,
                                })),
                            }
                        }),
                    })),
                })),
            }))
        }

        function buildSapTree(plantsData, matches) {
            return plantsData.map(plant => ({
                id: `plant-${plant.werks}`,
                kind: "plant",
                label: plant.label,
                plantError: plant.error,
                children: plant.usages.map(usage => ({
                    id: `use-${plant.werks}-${usage.stlan}`,
                    kind: "usage",
                    label: `用途 ${usage.stlan}`,
                    children: usage.alts.slice().sort(byStlal).map(alt => ({
                        id: alt.key,
                        label: `可选 ${alt.stlal}`,
                        type: "alt",
                        synced: matches.has(alt.key),
                        unsupported: alt.unsupported,
                        error: alt.error,
                        packaging: packagingBags(alt.items),
                        detail: alt,
                    })),
                })),
            }))
        }

        function collectVersions(projects) {
            const rows = []
            projects.forEach(project => {
                project.nodes.forEach(node => {
                    node.formulas.forEach(formula => {
                        formula.versions.forEach(version => rows.push(version))
                    })
                })
            })
            return rows
        }

        async function loadPlants() {
            const data = await api("/api/material/finished-boms/plants/")
            plants.value = data.results || []
        }

        function setProgress(text, percent) {
            loadText.value = text
            loadPercent.value = Math.max(0, Math.min(100, percent))
        }

        async function loadSap(matnr) {
            const chosen = plants.value.filter(plant => selectedPlants.value.includes(plant.code))
            let listedDone = 0
            const listed = await Promise.all(chosen.map(async plant => {
                try {
                    const data = await api(
                        `/api/sap/boms/?matnr=${encodeURIComponent(matnr)}&werks=${encodeURIComponent(plant.code)}`,
                    )
                    return { plant, rows: data.results || [], error: "" }
                } catch (error) {
                    return { plant, rows: [], error: error.message }
                } finally {
                    listedDone += 1
                    setProgress(
                        `正在查询 SAP BOM 列表（${listedDone}/${chosen.length}）`,
                        15 + Math.round(listedDone / chosen.length * 15),
                    )
                }
            }))
            const total = listed.reduce((count, group) => count + group.rows.length, 0)
            let done = 0
            const detailed = []
            for (const group of listed) {
                const usages = new Map()
                for (const row of group.rows) {
                    done += 1
                    setProgress(
                        `正在查询 BOM 明细（${done}/${total}）`,
                        30 + Math.round(done / total * 62),
                    )
                    const alt = await readAlt(row.matnr, row.werks, row.stlan, row.stlal, headerDate.value)
                    if (!usages.has(row.stlan)) usages.set(row.stlan, [])
                    usages.get(row.stlan).push(alt)
                    detailed.push(alt)
                }
                group.usages = [...usages.entries()].map(([stlan, alts]) => ({ stlan, alts }))
                group.werks = group.plant.code
                group.label = plantLabel(group.plant)
            }
            return { plantsData: listed, details: detailed }
        }

        function matchAll(versionRows, details) {
            const byVersion = new Map()
            const sapHits = new Set()
            versionRows.forEach(version => byVersion.set(version.id, []))
            details.forEach(detail => {
                if (detail.unsupported || !detail.shares) return
                versionRows.forEach(version => {
                    const kind = classify(version, detail.shares)
                    if (!kind) return
                    byVersion.get(version.id).push({
                        key: detail.key,
                        werks: detail.werks,
                        stlan: detail.stlan,
                        stlal: detail.stlal,
                        kind,
                        packaging: packagingBags(detail.items),
                    })
                    sapHits.add(detail.key)
                })
            })
            return { byVersion, sapHits }
        }

        function redraw() {
            const matched = matchAll(collectVersions(loadedProjects), loadedDetails)
            localTree.value = buildLocalTree(loadedProjects, matched.byVersion)
            sapTree.value = buildSapTree(loadedPlants, matched.sapHits)
            treeKey.value += 1
            hitKey.value = ""
        }

        function placeAlt(alt) {
            const existing = loadedDetails.findIndex(item => item.key === alt.key)
            if (existing >= 0) loadedDetails.splice(existing, 1, alt)
            else loadedDetails.push(alt)
            let plant = loadedPlants.find(item => item.werks === alt.werks)
            if (!plant) {
                const known = plants.value.find(item => item.code === alt.werks)
                const source = known || { code: alt.werks, name: "" }
                plant = {
                    plant: source,
                    werks: alt.werks,
                    label: plantLabel(source),
                    error: "",
                    usages: [],
                }
                loadedPlants.push(plant)
            }
            let usage = plant.usages.find(item => item.stlan === alt.stlan)
            if (!usage) {
                usage = { stlan: alt.stlan, alts: [] }
                plant.usages.push(usage)
            }
            const slot = usage.alts.findIndex(item => item.key === alt.key)
            if (slot >= 0) usage.alts.splice(slot, 1, alt)
            else usage.alts.push(alt)
        }

        function dropAlt(key) {
            loadedDetails = loadedDetails.filter(item => item.key !== key)
            loadedPlants.forEach(plant => {
                plant.usages.forEach(usage => {
                    usage.alts = usage.alts.filter(alt => alt.key !== key)
                })
                plant.usages = plant.usages.filter(usage => usage.alts.length > 0)
            })
            loadedPlants = loadedPlants.filter(plant => plant.usages.length > 0 || plant.error)
        }

        async function refreshRemoved(werks, stlan, stlal) {
            if (!loadedProjects || !material.value) {
                await loadAll()
                return
            }
            loading.value = true
            setProgress(`正在查询 SAP BOM 列表（${werks}）`, 30)
            try {
                const data = await api(
                    `/api/sap/boms/?matnr=${encodeURIComponent(material.value.sap_material_code)}&werks=${encodeURIComponent(werks)}`,
                )
                const stillThere = (data.results || []).some(
                    row => String(row.stlan) === String(stlan) && String(row.stlal) === String(stlal),
                )
                if (stillThere) {
                    setProgress(`正在刷新 SAP BOM（${werks} / 用途 ${stlan} / 可选 ${stlal}）`, 60)
                    const alt = await readAlt(
                        material.value.sap_material_code, werks, stlan, stlal, headerDate.value,
                    )
                    placeAlt(alt)
                } else {
                    dropAlt(sapKey(werks, stlan, stlal))
                }
                setProgress("正在计算同步标记", 90)
                await nextTick()
                redraw()
            } catch (error) {
                ElementPlus.ElMessage.error(error.message)
            } finally {
                loading.value = false
                loadText.value = ""
                loadPercent.value = 0
            }
        }

        async function refreshPublished(werks, stlan, stlal, datuv) {
            if (!loadedProjects || !material.value) {
                await loadAll()
                return
            }
            loading.value = true
            setProgress(`正在刷新 SAP BOM（${werks} / 用途 ${stlan} / 可选 ${stlal}）`, 40)
            try {
                const alt = await readAlt(
                    material.value.sap_material_code, werks, stlan, stlal, datuv,
                )
                placeAlt(alt)
                setProgress("正在计算同步标记", 90)
                await nextTick()
                redraw()
            } catch (error) {
                ElementPlus.ElMessage.error(error.message)
            } finally {
                loading.value = false
                loadText.value = ""
                loadPercent.value = 0
            }
        }

        async function loadAll() {
            if (!sapCode.value.trim()) {
                ElementPlus.ElMessage.warning("请输入成品编码")
                return
            }
            if (!selectedPlants.value.length) {
                ElementPlus.ElMessage.warning("请选择至少一个工厂")
                return
            }
            if (!headerDate.value) {
                ElementPlus.ElMessage.warning("请选择生效日期")
                return
            }
            loading.value = true
            setProgress("正在查询成品配方", 5)
            try {
                const tree = await api(
                    `/api/material/finished-boms/?sap_code=${encodeURIComponent(sapCode.value.trim())}`,
                )
                material.value = tree.material
                loadedProjects = tree.projects
                setProgress("正在查询 SAP BOM 列表", 15)
                const sap = await loadSap(tree.material.sap_material_code)
                loadedDetails = sap.details
                loadedPlants = sap.plantsData
                setProgress("正在计算同步标记", 96)
                await nextTick()
                redraw()
            } catch (error) {
                ElementPlus.ElMessage.error(error.message)
            } finally {
                loading.value = false
                loadText.value = ""
                loadPercent.value = 0
            }
        }

        function onLocalClick(data) {
            if (data.type === "version") openLocal(data.version)
            if (data.type === "sync") {
                hitKey.value = data.sapKey
                nextTick(() => sapTreeRef.value && sapTreeRef.value.setCurrentKey(data.sapKey))
            }
        }

        function openLocal(version) {
            current.value = version
            form.werks = selectedPlants.value[0] || ""
            form.stlan = "1"
            form.stlal = "01"
            form.bmeng = 1000
            form.datuv = headerDate.value
            form.ausch = 1
            form.stlst = "1"
            form.stktx = ""
            form.ztext = ""
            form.mergeColor = false
            form.packagingCode = ""
            form.packagingName = ""
            form.packagingQty = null
            checkResult.value = null
            localOpen.value = true
        }

        function openPackaging() {
            packagingQuery.q = ""
            packagingQuery.werks = form.werks || ""
            packagingRows.value = []
            packagingOpen.value = true
            searchPackaging()
        }

        function clearPackaging() {
            form.packagingCode = ""
            form.packagingName = ""
        }

        async function searchPackaging() {
            packagingLoading.value = true
            try {
                const params = new URLSearchParams()
                const text = packagingQuery.q.trim()
                if (text) params.set("q", text)
                if (packagingQuery.werks) params.set("werks", packagingQuery.werks)
                const data = await api(`/api/material/finished-boms/packaging/?${params}`)
                packagingRows.value = data.results || []
            } catch (error) {
                ElementPlus.ElMessage.error(error.message)
            } finally {
                packagingLoading.value = false
            }
        }

        function pickPackaging(row) {
            form.packagingCode = row.warehouse_code
            form.packagingName = row.name || ""
            packagingOpen.value = false
        }

        async function onSapClick(data) {
            if (data.type !== "alt" || data.error) return
            sapCurrent.value = data.detail
            sapOpen.value = true
            if (data.detail.namesLoaded) return
            const codes = []
            const seen = new Set()
            ;(data.detail.items || []).forEach(item => {
                const code = String(item.idnrk || "").trim()
                if (!code || seen.has(code)) return
                seen.add(code)
                codes.push(code)
            })
            if (!codes.length) {
                data.detail.namesLoaded = true
                return
            }
            try {
                const query = codes.map(code => `matnr=${encodeURIComponent(code)}`).join("&")
                const named = await api(`/api/sap/materials/?${query}`)
                const byCode = new Map((named.results || []).map(row => [row.matnr, row.maktx || ""]))
                data.detail.items = (data.detail.items || []).map(item => ({
                    ...item,
                    maktx: byCode.get(String(item.idnrk || "").trim()) || "",
                }))
                data.detail.namesLoaded = true
            } catch (error) {
                ElementPlus.ElMessage.error(error.message)
            }
        }

        function formReady() {
            if (!form.werks || !form.stlan || !form.stlal || !form.datuv || !Number.isInteger(form.bmeng) || !(form.bmeng > 0)) {
                ElementPlus.ElMessage.warning("请填写工厂、用途、可选号、整数基准数量和生效日期")
                return false
            }
            return true
        }

        async function runCheck() {
            if (!formReady() || !material.value) return
            checking.value = true
            try {
                const data = await api(
                    `/api/sap/boms/?matnr=${encodeURIComponent(material.value.sap_material_code)}&werks=${encodeURIComponent(form.werks)}`,
                )
                const exists = (data.results || []).some(
                    row => row.stlan === form.stlan && row.stlal === form.stlal,
                )
                checkResult.value = exists ? "update" : "create"
            } catch (error) {
                checkResult.value = null
                ElementPlus.ElMessage.error(error.message)
            } finally {
                checking.value = false
            }
        }

        async function submit(mode) {
            if (!formReady() || missingNamesOfForm.value.length) return
            const packagingCode = (form.packagingCode || "").trim()
            const packagingQty = form.packagingQty
            const hasPackaging = !!packagingCode
            const hasPackagingQty = packagingQty !== null && packagingQty !== undefined && packagingQty !== ""
            if (hasPackaging !== hasPackagingQty) {
                ElementPlus.ElMessage.warning("包装袋和数量必须同时填写")
                return
            }
            if (hasPackagingQty && !(Number(packagingQty) > 0)) {
                ElementPlus.ElMessage.warning("包装袋数量必须大于 0")
                return
            }
            if (mode === "update") {
                try {
                    await ElementPlus.ElMessageBox.confirm(
                        "将用当前配方整表覆盖该 SAP BOM，SAP 里多出来的行不会保留。",
                        "确认修改",
                        { type: "warning" },
                    )
                } catch (error) {
                    return
                }
            }
            saving.value = true
            try {
                const body = {
                    formula_id: current.value.id,
                    werks: form.werks,
                    stlan: form.stlan,
                    stlal: form.stlal,
                    bmeng: form.bmeng,
                    datuv: form.datuv,
                    ausch: form.ausch,
                    stlst: form.stlst,
                    stktx: form.stktx,
                    ztext: form.ztext,
                    merge_color: form.mergeColor,
                    mode,
                }
                if (hasPackaging) {
                    body.packaging_code = packagingCode
                    body.packaging_qty = packagingQty
                }
                await api("/api/material/finished-boms/publish/", {
                    method: "POST",
                    body: JSON.stringify(body),
                })
                ElementPlus.ElMessage.success(mode === "create" ? "已发布" : "已修改")
                const published = {
                    werks: form.werks,
                    stlan: form.stlan,
                    stlal: form.stlal,
                    datuv: form.datuv,
                }
                localOpen.value = false
                await refreshPublished(published.werks, published.stlan, published.stlal, published.datuv)
            } catch (error) {
                ElementPlus.ElMessage.error(error.message)
            } finally {
                saving.value = false
            }
        }

        async function removeSap() {
            if (!sapCurrent.value) return
            try {
                await ElementPlus.ElMessageBox.confirm("删除后不可从本页恢复。", "删除该 BOM", { type: "warning" })
            } catch (error) {
                return
            }
            deleting.value = true
            const row = sapCurrent.value
            try {
                await api(
                    `/api/sap/boms/${encodeURIComponent(material.value.sap_material_code)}/${encodeURIComponent(row.werks)}/${encodeURIComponent(row.stlan)}/${encodeURIComponent(row.stlal)}/`,
                    { method: "DELETE" },
                )
                ElementPlus.ElMessage.success("已删除")
                const removed = { werks: row.werks, stlan: row.stlan, stlal: row.stlal }
                sapOpen.value = false
                await refreshRemoved(removed.werks, removed.stlan, removed.stlal)
            } catch (error) {
                ElementPlus.ElMessage.error(error.message)
            } finally {
                deleting.value = false
            }
        }

        loadPlants().catch(error => ElementPlus.ElMessage.error(error.message))

        return {
            sapCode, plants, selectedPlants, headerDate, loading, loadText, loadPercent, material,
            localTree, sapTree, treeKey, hitKey, sapTreeRef,
            localOpen, current, form, checkResult, checking, saving,
            sapOpen, sapCurrent, deleting,
            packagingOpen, packagingQuery, packagingRows, packagingLoading, packagingLabel,
            missingNames: missingNamesOfForm, preview,
            plantLabel, packagingTitle, rowClass, loadAll, onLocalClick, onSapClick, runCheck, submit, removeSap,
            openPackaging, clearPackaging, searchPackaging, pickPackaging,
        }
    },
}).use(ElementPlus, { locale: ElementPlusLocaleZhCn }).mount("#app")
