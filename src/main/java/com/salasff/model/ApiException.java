package com.salasff.model;

public class ApiException extends Exception {
    private final int errorCode;

    public ApiException(String message, int errorCode) {
        super(message);
        this.errorCode = errorCode;
    }

    public ApiException(String message) {
        this(message, -1);
    }

    public int getErrorCode() { return errorCode; }
}
