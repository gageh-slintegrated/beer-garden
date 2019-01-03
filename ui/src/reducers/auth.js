import {
  USER_LOGIN_BEGIN,
  USER_LOGIN_SUCCESS,
  USER_LOGIN_FAILURE,
  USER_LOGOUT_BEGIN,
  USER_LOGOUT_SUCCESS,
  USER_LOGOUT_FAILURE,
} from "../constants/ActionTypes";
import { getCookie, deleteCookie } from "../utils";

const REFRESH_COOKIE_NAME = "refresh_id";
const sessionCookie = getCookie(REFRESH_COOKIE_NAME);

const initialState = {
  userData: {},
  isAuthenticated: sessionCookie ? true : false,
  userLoading: false,
  userError: null,
};

export default function authReducer(state = initialState, action) {
  switch (action.type) {
    case USER_LOGIN_BEGIN:
      return {
        ...state,
        userData: {},
        isAuthenticated: false,
        userLoading: true,
        userError: null,
      };
    case USER_LOGIN_SUCCESS:
      return {
        ...state,
        userLoading: false,
        isAuthenticated: true,
        userError: null,
        userData: action.payload.data,
      };
    case USER_LOGIN_FAILURE:
      deleteCookie(REFRESH_COOKIE_NAME);
      return {
        ...state,
        userData: {},
        isAuthenticated: false,
        userLoading: false,
        userError: action.payload.error,
      };
    case USER_LOGOUT_BEGIN:
      return {
        ...state,
        userLoading: true,
      };
    case USER_LOGOUT_FAILURE:
      return {
        ...state,
        userLoading: false,
        userError: action.payload.error,
      };
    case USER_LOGOUT_SUCCESS:
      return {
        ...state,
        userData: {},
        isAuthenticated: false,
        userLoading: false,
        userError: null,
      };

    default:
      return state;
  }
}
