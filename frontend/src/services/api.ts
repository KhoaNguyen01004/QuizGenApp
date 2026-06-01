import axios from 'axios';
import { GenerateResponse, StatusResponse, ResultResponse, QuizMode } from '../types';

const API_URL = 'http://localhost:8000';

export const api = {
  async generateQuiz(file: File, mode: QuizMode, numQuestions: number): Promise<GenerateResponse> {
    // C-3: single FormData using the 'pdf' field name that the backend expects
    const formData = new FormData();
    formData.append('pdf', file);
    formData.append('mode', mode);
    formData.append('num_questions', numQuestions.toString());

    const response = await axios.post<GenerateResponse>(`${API_URL}/generate`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  async getStatus(jobId: string): Promise<StatusResponse> {
    const response = await axios.get<StatusResponse>(`${API_URL}/status/${jobId}`);
    return response.data;
  },

  async getResult(jobId: string): Promise<ResultResponse> {
    const response = await axios.get<ResultResponse>(`${API_URL}/result/${jobId}`);
    return response.data;
  }
};
