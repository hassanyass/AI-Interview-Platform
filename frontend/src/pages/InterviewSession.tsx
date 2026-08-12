import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ArrowLeft, Play, Settings, Clock, BrainCircuit } from 'lucide-react'
import { API_BASE_URL } from '../lib/api'

export default function InterviewSession() {
  const { id } = useParams()
  const { getAccessToken } = useAuth()
  const [session, setSession] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    async function fetchSession() {
      try {
        const token = await getAccessToken()
        const res = await fetch(`${API_BASE_URL}/api/v1/interviews/${id}`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        
        if (!res.ok) {
          throw new Error("Failed to load interview session")
        }
        
        setSession(await res.json())
      } catch (err: any) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    
    fetchSession()
  }, [id])

  if (loading) return <div className="flex justify-center p-20">Loading session...</div>

  if (error) return (
    <div className="max-w-4xl mx-auto py-10 px-4">
      <div className="bg-red-50 text-red-700 p-6 rounded-lg text-center">
        <p className="font-semibold mb-2">Error</p>
        <p>{error}</p>
        <Link to="/dashboard" className="text-blue-600 hover:underline mt-4 inline-block">Return to Dashboard</Link>
      </div>
    </div>
  )

  return (
    <div className="max-w-4xl mx-auto py-10 px-4">
      <div className="mb-6">
        <Link to="/dashboard" className="text-gray-500 hover:text-gray-900 flex items-center space-x-2 w-fit">
          <ArrowLeft size={16} /> <span>Back to Dashboard</span>
        </Link>
      </div>

      <div className="flex justify-between items-start mb-8">
        <div>
          <div className="flex items-center space-x-3 mb-2">
            <h1 className="text-3xl font-bold text-gray-900">{session.role}</h1>
            <span className="bg-blue-100 text-blue-800 text-xs px-3 py-1 rounded-full uppercase tracking-wide font-semibold">
              {session.status}
            </span>
          </div>
          <p className="text-gray-500">Created on {new Date(session.created_at).toLocaleString()}</p>
        </div>
        
        <button 
          disabled
          className="bg-gray-300 text-gray-600 px-6 py-3 rounded-lg font-semibold flex items-center space-x-2 cursor-not-allowed"
          title="Interview execution is part of Phase 3"
        >
          <Play size={20} fill="currentColor" />
          <span>Start Interview (Phase 3)</span>
        </button>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="bg-gray-50 px-6 py-4 border-b border-gray-200 flex items-center space-x-2">
          <Settings size={20} className="text-gray-500" />
          <h2 className="text-lg font-semibold text-gray-800">Session Configuration</h2>
        </div>
        
        <div className="p-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
            <div>
              <p className="text-sm text-gray-500 mb-1">Level</p>
              <p className="font-medium capitalize">{session.level}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500 mb-1">Language</p>
              <p className="font-medium uppercase">{session.language}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500 mb-1 flex items-center"><Clock size={14} className="mr-1"/> Duration</p>
              <p className="font-medium">{session.configuration?.duration} mins</p>
            </div>
            <div>
              <p className="text-sm text-gray-500 mb-1 flex items-center"><BrainCircuit size={14} className="mr-1"/> Thinking Time</p>
              <p className="font-medium">{session.configuration?.thinking_time} secs</p>
            </div>
          </div>
          
          {session.configuration?.job_description && (
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">Job Description Context</p>
              <div className="bg-gray-50 p-4 rounded-lg text-sm text-gray-600 whitespace-pre-wrap border border-gray-100 max-h-64 overflow-y-auto">
                {session.configuration.job_description}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
