import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ArrowLeft, PlayCircle } from 'lucide-react'
import { API_BASE_URL } from '../lib/api'

export default function NewInterview() {
  const { getAccessToken } = useAuth()
  const navigate = useNavigate()
  
  const [profile, setProfile] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const [formData, setFormData] = useState({
    role: 'Software Engineer',
    level: 'mid',
    language: 'en',
    duration: 15,
    thinking_time: 60,
    job_description: ''
  })

  useEffect(() => {
    async function fetchProfile() {
      const token = await getAccessToken()
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/profiles/me`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        if (res.ok) {
          const data = await res.json()
          setProfile(data)
          if (data.confirmed_level) {
            setFormData(prev => ({ ...prev, level: data.confirmed_level }))
          } else if (data.recommended_level) {
            setFormData(prev => ({ ...prev, level: data.recommended_level }))
          }
        }
      } catch (err) {
        console.error("Failed to fetch profile", err)
      } finally {
        setLoading(false)
      }
    }
    fetchProfile()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError('')

    try {
      const token = await getAccessToken()
      const res = await fetch(`${API_BASE_URL}/api/v1/interviews/`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ configuration: formData })
      })

      if (!res.ok) {
        const errData = await res.json()
        throw new Error(errData.detail || "Failed to create session")
      }

      const session = await res.json()
      navigate(`/interviews/${session.id}`)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="flex justify-center p-20">Loading...</div>

  return (
    <div className="max-w-3xl mx-auto py-10 px-4">
      <div className="mb-6">
        <Link to="/dashboard" className="text-gray-500 hover:text-gray-900 flex items-center space-x-2 w-fit">
          <ArrowLeft size={16} /> <span>Back to Dashboard</span>
        </Link>
      </div>

      <h1 className="text-3xl font-bold text-gray-900 mb-8">Configure New Interview</h1>

      {error && <div className="mb-6 bg-red-50 text-red-700 p-4 rounded-lg">{error}</div>}
      
      {!profile?.confirmed_level && (
        <div className="mb-8 bg-yellow-50 border border-yellow-200 text-yellow-800 p-4 rounded-lg text-sm">
          <strong>Note:</strong> You haven't confirmed your SWE level in your profile. We are using {profile?.recommended_level ? `the recommended level (${profile.recommended_level})` : 'a default level'} for now.
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-white p-8 rounded-xl border shadow-sm space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
            <input 
              type="text" 
              required
              value={formData.role}
              onChange={e => setFormData({...formData, role: e.target.value})}
              className="w-full p-2 border rounded-lg focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">SWE Level</label>
            <select 
              value={formData.level}
              onChange={e => setFormData({...formData, level: e.target.value})}
              className="w-full p-2 border rounded-lg focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="junior">Junior</option>
              <option value="mid">Mid-Level</option>
              <option value="senior">Senior</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Language</label>
            <select 
              value={formData.language}
              onChange={e => setFormData({...formData, language: e.target.value})}
              className="w-full p-2 border rounded-lg focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="en">English</option>
              <option value="ar">Arabic</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Duration (minutes)</label>
            <input 
              type="number" 
              min="5" max="120"
              required
              value={formData.duration}
              onChange={e => setFormData({...formData, duration: parseInt(e.target.value)})}
              className="w-full p-2 border rounded-lg focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Thinking Time (seconds)</label>
            <input 
              type="number" 
              min="10" max="300"
              required
              value={formData.thinking_time}
              onChange={e => setFormData({...formData, thinking_time: parseInt(e.target.value)})}
              className="w-full p-2 border rounded-lg focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Job Description (Optional)</label>
          <textarea 
            rows={4}
            value={formData.job_description}
            onChange={e => setFormData({...formData, job_description: e.target.value})}
            className="w-full p-2 border rounded-lg focus:ring-blue-500 focus:border-blue-500 text-sm"
            placeholder="Paste a job description here to contextualize the interview questions..."
          />
        </div>

        <div className="pt-4 flex justify-end">
          <button 
            type="submit"
            disabled={submitting}
            className="flex items-center space-x-2 bg-blue-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50"
          >
            <span>{submitting ? 'Creating...' : 'Create Session'}</span>
            <PlayCircle size={18} />
          </button>
        </div>
      </form>
    </div>
  )
}
