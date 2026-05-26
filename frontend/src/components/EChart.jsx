// 轻量 ECharts 封装：传入 option，自动初始化/更新/随窗口自适应。
import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

export default function EChart({ option, style }) {
  const ref = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    chartRef.current = echarts.init(ref.current)
    const onResize = () => chartRef.current && chartRef.current.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chartRef.current && chartRef.current.dispose()
    }
  }, [])

  useEffect(() => {
    if (chartRef.current && option) {
      chartRef.current.setOption(option, true)
    }
  }, [option])

  return <div ref={ref} className="chart" style={style} />
}
